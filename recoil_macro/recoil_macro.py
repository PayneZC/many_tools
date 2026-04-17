"""
Windows 压枪宏（Logitech Lua 脚本的 Python 实现）。

与 Lua 脚本对应的功能：
1) 按住鼠标右键（button 2）时启用压枪开关。
2) 在开关生效时，按住鼠标左键持续向下移动鼠标。
3) 跟随模式：按住右键激活，按住左键跟踪屏幕中心目标。
"""

from __future__ import annotations

import ctypes
import random
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageGrab, ImageTk
from pynput import mouse, keyboard

try:
    from .follow_core import (
        RobustPointTracker,
        TRACK_REGION_HALF,
        TrackerConfig,
        to_gray,
    )
except ImportError:
    from follow_core import (
        RobustPointTracker,
        TRACK_REGION_HALF,
        TrackerConfig,
        to_gray,
    )


VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

user32 = ctypes.windll.user32


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_cursor_pos(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)


def is_pressed(vk_code: int) -> bool:
    return (user32.GetAsyncKeyState(vk_code) & 0x8000) != 0


def move_mouse_relative(dx: int, dy: int) -> None:
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


@dataclass
class RuntimeState:
    recoil_enabled: bool = True
    switch_enabled: bool = False
    running_loop: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    mode: str = "recoil"
    lock_mouse_active: bool = False
    lock_mouse_running: bool = False
    hotkey_enabled: bool = False
    sensitivity: float = 0.8
    lock_start_pos: tuple[int, int] | None = None
    debug_enabled: bool = False
    debug_locked: bool = False
    debug_score: float = 0.0
    debug_lost_count: int = 0
    debug_target_screen: tuple[int, int] | None = None
    debug_aim_screen: tuple[int, int] | None = None
    debug_output_move: tuple[int, int] = (0, 0)
    debug_raw_offset: tuple[float, float] = (0.0, 0.0)
    debug_points: int = 0
    debug_region: tuple[int, int, int, int] | None = None
    debug_target_local: tuple[float, float] | None = None
    debug_aim_local: tuple[float, float] | None = None
    game_mode: bool = False
    debug_capture_blocked: bool = False


def run_recoil_loop(state: RuntimeState) -> None:
    with state.lock:
        if state.running_loop:
            return
        state.running_loop = True

    try:
        time.sleep(0.001)
        y_count = 0
        while is_pressed(VK_LBUTTON):
            with state.lock:
                if not (state.recoil_enabled and state.switch_enabled):
                    break

            y_step = 28 if y_count == 0 else 14 + y_count
            if y_count < 8:
                y_count += 1

            move_mouse_relative(0, y_step)
            time.sleep(0.018)
    finally:
        with state.lock:
            state.running_loop = False


def capture_screen(region: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = region
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


DEAD_ZONE = 2
MAX_REACQUIRE_FAILURES = 8
RENDER_WAIT = 0.009
LOOP_IDLE_WAIT = 0.006
MAX_CONTROL_STEP = 30
VELOCITY_FEEDFORWARD = 0.45
RETURN_BIAS_MAX = 4
RETURN_BIAS_TRIGGER = 5.0
RETURN_BIAS_COOLDOWN = 0.09
CAPTURE_BLOCK_STD = 1.5
CAPTURE_BLOCK_FRAMES = 12


def run_lock_mouse_loop(state: RuntimeState) -> None:
    with state.lock:
        if state.lock_mouse_running:
            return
        state.lock_mouse_running = True

    with state.lock:
        start_pos = state.lock_start_pos
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    if start_pos is None:
        sx = screen_w // 2
        sy = screen_h // 2
        start_pos = (sx, sy)

    full_region = (0, 0, screen_w, screen_h)
    target_local = (float(start_pos[0]), float(start_pos[1]))
    init_gray = to_gray(capture_screen(full_region))
    tracker = RobustPointTracker(
        TrackerConfig(
            lock_half=18,
            init_half=30,
            search_half=135,
            min_std=5.0,
            min_edge_pixels=8,
            min_score=0.34,
            min_reacquire_score=0.26,
            min_psr=4.2,
            min_appearance=0.30,
            top_k=6,
            update_alpha=0.05,
            max_jump=48.0,
            max_reacquire_jump=90.0,
            max_soft_lost=12,
        )
    )
    tracker.initialize(init_gray, target_local)
    filt_x = 0.0
    filt_y = 0.0
    last_bias_time = 0.0
    blocked_frames = 0

    try:
        while True:
            with state.lock:
                if not state.lock_mouse_active:
                    break
            if not (is_pressed(VK_LBUTTON) and is_pressed(VK_RBUTTON)):
                break

            curr_gray = to_gray(capture_screen(full_region))
            if float(np.std(curr_gray)) <= CAPTURE_BLOCK_STD:
                blocked_frames += 1
            else:
                blocked_frames = max(0, blocked_frames - 2)
            capture_blocked = blocked_frames >= CAPTURE_BLOCK_FRAMES

            moved = False
            cursor_x, cursor_y = get_cursor_pos()
            aim_x = float(cursor_x)
            aim_y = float(cursor_y)

            if capture_blocked:
                locked, dx, dy = False, 0.0, 0.0
            else:
                locked, dx, dy = tracker.update(curr_gray, (aim_x, aim_y))
                if not locked and tracker.lost_count >= MAX_REACQUIRE_FAILURES:
                    if tracker.target_center is not None:
                        tracker.initialize(curr_gray, tracker.target_center)
                    else:
                        tracker.initialize(curr_gray, (aim_x, aim_y))

            if locked:
                with state.lock:
                    gain = state.sensitivity

                # 高灵敏度时压缩有效增益，减少过冲导致的抖动和乱跳
                effective_gain = gain if gain <= 0.8 else (0.8 + (gain - 0.8) * 0.42)
                ff_x = tracker.velocity[0] * VELOCITY_FEEDFORWARD
                ff_y = tracker.velocity[1] * VELOCITY_FEEDFORWARD
                cmd_x = (dx + ff_x) * effective_gain
                cmd_y = (dy + ff_y) * effective_gain

                # 控制输出低通滤波；高灵敏度时加重平滑
                smooth_alpha = 0.28 if gain >= 0.8 else 0.42
                filt_x = filt_x * (1.0 - smooth_alpha) + cmd_x * smooth_alpha
                filt_y = filt_y * (1.0 - smooth_alpha) + cmd_y * smooth_alpha

                move_x = int(round(filt_x))
                move_y = int(round(filt_y))
                dynamic_limit = MAX_CONTROL_STEP + int(min(18.0, abs(tracker.velocity[0]) + abs(tracker.velocity[1])))
                move_x = max(-dynamic_limit, min(dynamic_limit, move_x))
                move_y = max(-dynamic_limit, min(dynamic_limit, move_y))

                adaptive_dead_zone = DEAD_ZONE + (1 if gain >= 0.8 else 0)
                if abs(move_x) <= adaptive_dead_zone:
                    move_x = 0
                if abs(move_y) <= adaptive_dead_zone:
                    move_y = 0

                # 跟随回到标记点时，随机增加 0-4 像素方向偏差（防过于机械）
                now = time.time()
                near_mark = abs(dx) <= RETURN_BIAS_TRIGGER and abs(dy) <= RETURN_BIAS_TRIGGER
                if near_mark and (now - last_bias_time) >= RETURN_BIAS_COOLDOWN:
                    bx = random.choice((-1, 1)) * random.randint(0, RETURN_BIAS_MAX)
                    by = random.choice((-1, 1)) * random.randint(0, RETURN_BIAS_MAX)
                    move_x += bx
                    move_y += by
                    last_bias_time = now

                if move_x != 0 or move_y != 0:
                    move_mouse_relative(move_x, move_y)
                    moved = True
            else:
                move_x = 0
                move_y = 0
                filt_x *= 0.72
                filt_y *= 0.72

            with state.lock:
                state.debug_locked = locked
                state.debug_score = tracker.last_score
                state.debug_lost_count = tracker.lost_count
                state.debug_raw_offset = (dx, dy)
                state.debug_output_move = (move_x, move_y)
                state.debug_points = tracker.last_points
                state.debug_aim_screen = (cursor_x, cursor_y)
                state.debug_capture_blocked = capture_blocked
                if tracker.target_center is not None:
                    state.debug_target_screen = (
                        int(round(tracker.target_center[0])),
                        int(round(tracker.target_center[1])),
                    )
                    view_cx, view_cy = state.debug_target_screen
                else:
                    state.debug_target_screen = None
                    view_cx, view_cy = cursor_x, cursor_y
                x1 = max(0, view_cx - TRACK_REGION_HALF)
                y1 = max(0, view_cy - TRACK_REGION_HALF)
                x2 = min(screen_w, view_cx + TRACK_REGION_HALF)
                y2 = min(screen_h, view_cy + TRACK_REGION_HALF)
                state.debug_region = (x1, y1, x2, y2)
                state.debug_aim_local = (aim_x - x1, aim_y - y1)
                if tracker.target_center is not None:
                    state.debug_target_local = (
                        tracker.target_center[0] - x1,
                        tracker.target_center[1] - y1,
                    )
                else:
                    state.debug_target_local = None

            time.sleep(RENDER_WAIT if moved else LOOP_IDLE_WAIT)

    finally:
        with state.lock:
            state.lock_mouse_active = False
            state.lock_mouse_running = False
            state.lock_start_pos = None
            state.debug_locked = False
            state.debug_score = 0.0
            state.debug_lost_count = 0
            state.debug_target_screen = None
            state.debug_aim_screen = None
            state.debug_output_move = (0, 0)
            state.debug_raw_offset = (0.0, 0.0)
            state.debug_points = 0
            state.debug_region = None
            state.debug_target_local = None
            state.debug_aim_local = None
            state.debug_capture_blocked = False


def main() -> None:
    state = RuntimeState()
    root = tk.Tk()
    root.title("压枪脚本")
    root.geometry("360x280")
    root.resizable(False, False)

    tip1 = tk.Label(root, text="脚本运行中", font=("Microsoft YaHei UI", 12, "bold"))
    tip1.pack(pady=(15, 5))

    mode_label = tk.Label(root, text="当前模式：压枪模式", font=("Microsoft YaHei UI", 10))
    mode_label.pack(pady=(0, 5))

    def toggle_mode():
        with state.lock:
            if state.mode == "recoil":
                state.mode = "lock"
                mode_label.config(text="当前模式：跟随模式")
                btn.config(text="切换为压枪模式")
                tip2.config(text="按住右键激活，按住左键跟随目标区域")
                sens_frame.pack(after=btn, pady=(0, 5))
            else:
                state.mode = "recoil"
                mode_label.config(text="当前模式：压枪模式")
                btn.config(text="切换为跟随模式")
                tip2.config(text="按住右键激活，按住左键执行压枪")
                sens_frame.pack_forget()

    btn = tk.Button(root, text="切换为跟随模式", command=toggle_mode, width=20, height=1)
    btn.pack(pady=(0, 5))

    sens_frame = tk.Frame(root)
    sens_label = tk.Label(sens_frame, text="跟随灵敏度:", font=("Microsoft YaHei UI", 9))
    sens_label.pack(side=tk.LEFT, padx=(0, 5))

    def on_sensitivity_change(val):
        state.sensitivity = float(val)

    sens_var = tk.DoubleVar(value=0.8)
    sens_scale = tk.Scale(sens_frame, from_=0.1, to=2.0, resolution=0.1,
                          orient=tk.HORIZONTAL, variable=sens_var, length=150,
                          command=on_sensitivity_change)
    sens_scale.pack(side=tk.LEFT)

    hotkey_var = tk.BooleanVar(value=False)
    hotkey_check = tk.Checkbutton(root, text="启用快捷键切换模式（F6）", variable=hotkey_var, font=("Microsoft YaHei UI", 9))
    hotkey_check.pack(pady=(0, 5))

    debug_var = tk.BooleanVar(value=False)
    debug_check = tk.Checkbutton(root, text="显示跟随调试窗口", variable=debug_var, font=("Microsoft YaHei UI", 9))
    debug_check.pack(pady=(0, 5))
    preview_var = tk.BooleanVar(value=True)
    preview_check = tk.Checkbutton(root, text="调试窗口显示锁定框预览", variable=preview_var, font=("Microsoft YaHei UI", 9))
    preview_check.pack(pady=(0, 5))
    game_mode_var = tk.BooleanVar(value=True)
    game_mode_check = tk.Checkbutton(root, text="游戏兼容模式（自动最小化/禁用预览）", variable=game_mode_var, font=("Microsoft YaHei UI", 9))
    game_mode_check.pack(pady=(0, 5))

    def on_hotkey_press(key):
        try:
            if key == keyboard.Key.f6:
                with state.lock:
                    enabled = state.hotkey_enabled
                if enabled:
                    root.after(0, toggle_mode)
        except Exception:
            pass

    def update_hotkey_state():
        with state.lock:
            state.hotkey_enabled = hotkey_var.get()

    hotkey_var.trace_add("write", lambda *args: update_hotkey_state())

    def update_game_mode_state():
        with state.lock:
            state.game_mode = game_mode_var.get()
        if game_mode_var.get():
            preview_var.set(False)
            debug_var.set(False)

    game_mode_var.trace_add("write", lambda *args: update_game_mode_state())
    update_game_mode_state()

    debug_win: tk.Toplevel | None = None
    debug_text: tk.Label | None = None
    debug_preview: tk.Label | None = None
    preview_photo: ImageTk.PhotoImage | None = None
    last_preview_time = 0.0

    def build_debug_window() -> None:
        nonlocal debug_win, debug_text, debug_preview
        if debug_win is not None and debug_win.winfo_exists():
            return
        debug_win = tk.Toplevel(root)
        debug_win.title("跟随调试信息")
        debug_win.geometry("420x560")
        debug_win.resizable(False, False)
        debug_win.attributes("-topmost", True)
        debug_text = tk.Label(debug_win, justify=tk.LEFT, anchor="nw", font=("Consolas", 10))
        debug_text.pack(fill=tk.X, padx=10, pady=(10, 6))
        debug_preview = tk.Label(
            debug_win,
            text="预览未启动",
            justify=tk.CENTER,
            anchor="center",
            bg="#1e1e1e",
            fg="#d0d0d0",
            width=56,
            height=20,
        )
        debug_preview.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        def on_debug_close() -> None:
            debug_var.set(False)
            if debug_win is not None:
                debug_win.withdraw()

        debug_win.protocol("WM_DELETE_WINDOW", on_debug_close)

    def sync_debug_window() -> None:
        nonlocal debug_win, debug_text, debug_preview, preview_photo, last_preview_time
        enabled = debug_var.get()
        with state.lock:
            state.debug_enabled = enabled
            locked = state.debug_locked
            score = state.debug_score
            lost = state.debug_lost_count
            target = state.debug_target_screen
            aim = state.debug_aim_screen
            out_move = state.debug_output_move
            raw_off = state.debug_raw_offset
            points_cnt = state.debug_points
            mode_now = state.mode
            running = state.lock_mouse_running
            region_dbg = state.debug_region
            target_local = state.debug_target_local
            aim_local = state.debug_aim_local
            capture_blocked = state.debug_capture_blocked
            game_mode_enabled = state.game_mode

        if game_mode_enabled:
            enabled = False

        if enabled:
            build_debug_window()
            if debug_win is not None:
                debug_win.deiconify()
                debug_win.lift()
        else:
            if debug_win is not None and debug_win.winfo_exists():
                debug_win.withdraw()

        if enabled and debug_text is not None:
            if target is None:
                target_text = "N/A"
            else:
                target_text = f"{target[0]}, {target[1]}"
            if aim is None:
                aim_text = "N/A"
            else:
                aim_text = f"{aim[0]}, {aim[1]}"

            debug_text.config(
                text=(
                    f"模式: {'跟随' if mode_now == 'lock' else '压枪'}\n"
                    f"跟随线程: {'运行中' if running else '空闲'}\n"
                    f"锁定状态: {'LOCKED' if locked else 'LOST'}\n"
                    f"匹配分数: {score:.3f}\n"
                    f"失锁计数: {lost}\n"
                    f"跟踪点数: {points_cnt}\n"
                    f"采集状态: {'BLOCKED' if capture_blocked else 'OK'}\n"
                    f"目标坐标: {target_text}\n"
                    f"准星坐标: {aim_text}\n"
                    f"原始偏移(dx,dy): ({raw_off[0]:.2f}, {raw_off[1]:.2f})\n"
                    f"输出移动(dx,dy): ({out_move[0]}, {out_move[1]})"
                )
            )

        if enabled and preview_var.get() and running and region_dbg is not None and debug_preview is not None:
            now = time.time()
            if now - last_preview_time >= 0.12:
                last_preview_time = now
                try:
                    preview_img = capture_screen(region_dbg)
                    if aim_local is not None:
                        cv2.circle(
                            preview_img,
                            (int(round(aim_local[0])), int(round(aim_local[1]))),
                            5,
                            (0, 255, 0),
                            1,
                        )
                    if target_local is not None:
                        tx = int(round(target_local[0]))
                        ty = int(round(target_local[1]))
                        cv2.rectangle(preview_img, (tx - 26, ty - 26), (tx + 26, ty + 26), (0, 0, 255), 2)
                        cv2.circle(preview_img, (tx, ty), 3, (255, 255, 0), -1)
                        if aim_local is not None:
                            cv2.line(
                                preview_img,
                                (int(round(aim_local[0])), int(round(aim_local[1]))),
                                (tx, ty),
                                (255, 120, 0),
                                1,
                            )
                    else:
                        cv2.putText(
                            preview_img,
                            "LOST",
                            (20, 34),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 0, 255),
                            2,
                        )

                    h, w = preview_img.shape[:2]
                    scale = min(380.0 / w, 300.0 / h)
                    disp_w = max(1, int(round(w * scale)))
                    disp_h = max(1, int(round(h * scale)))
                    preview_img = cv2.resize(preview_img, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
                    rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    preview_photo = ImageTk.PhotoImage(image=pil_img)
                    debug_preview.configure(image=preview_photo, text="")
                    debug_preview.image = preview_photo
                except Exception:
                    debug_preview.configure(text="预览抓取失败", image="")
                    debug_preview.image = None
        elif enabled and preview_var.get() and debug_preview is not None:
            debug_preview.configure(text="等待跟随线程启动...", image="")
            debug_preview.image = None
        elif enabled and debug_preview is not None:
            debug_preview.configure(text="已关闭预览显示", image="")
            debug_preview.image = None

        root.after(60, sync_debug_window)

    root.after(60, sync_debug_window)

    tip2 = tk.Label(root, text="按住右键激活，按住左键执行压枪")
    tip2.pack()
    tip3 = tk.Label(root, text="关闭此窗口将退出程序", fg="gray")
    tip3.pack(pady=(5, 0))

    def on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if button == mouse.Button.right:
            with state.lock:
                state.switch_enabled = pressed
                if not pressed:
                    state.lock_mouse_active = False
            return

        if button == mouse.Button.left:
            if pressed:
                with state.lock:
                    current_mode = state.mode
                    can_run = (state.recoil_enabled and state.switch_enabled
                               and not state.running_loop and not state.lock_mouse_running)

                if current_mode == "recoil":
                    if can_run:
                        t = threading.Thread(target=run_recoil_loop, args=(state,), daemon=True)
                        t.start()
                else:
                    if can_run:
                        with state.lock:
                            state.lock_mouse_active = True
                            state.lock_start_pos = (x, y)
                            game_mode_on = state.game_mode
                        t = threading.Thread(target=run_lock_mouse_loop, args=(state,), daemon=True)
                        t.start()
                        if game_mode_on:
                            root.after(0, root.iconify)
            else:
                with state.lock:
                    state.lock_mouse_active = False

    listener = mouse.Listener(on_click=on_click)
    listener.start()

    kb_listener = keyboard.Listener(on_press=on_hotkey_press)
    kb_listener.start()

    def on_close() -> None:
        try:
            listener.stop()
            kb_listener.stop()
            if debug_win is not None and debug_win.winfo_exists():
                debug_win.destroy()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
