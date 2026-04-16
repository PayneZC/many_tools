"""
Windows 压枪宏（Logitech Lua 脚本的 Python 实现）。

与 Lua 脚本对应的功能：
1) 按住鼠标右键（button 2）时启用压枪开关。
2) 在开关生效时，按住鼠标左键持续向下移动鼠标。
"""

from __future__ import annotations

import ctypes
import math
import threading
import time
import tkinter as tk
import random
from dataclasses import dataclass, field

from pynput import mouse, keyboard


# WinAPI 常量
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_MOVE_ABSOLUTE = 0x0001
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
    recorded_pos: tuple[int, int] | None = None
    lock_mouse_active: bool = False
    lock_mouse_running: bool = False
    hotkey_enabled: bool = False
    skip_next_correction: bool = False


def run_recoil_loop(state: RuntimeState) -> None:
    # 原子化进入“单实例压枪循环”。
    with state.lock:
        if state.running_loop:
            return
        state.running_loop = True

    try:
        time.sleep(0.001)  # 对应 Lua 的 Sleep(1)
        y_count = 0
        # 只要左键仍被按住，就持续执行压枪。
        while is_pressed(VK_LBUTTON):
            with state.lock:
                if not (state.recoil_enabled and state.switch_enabled):
                    break

            # 对应你保留的 Lua 曲线：
            # 首次下压 28；之后为 14 + y_count；y_count 最大到 8。
            y_step = 28 if y_count == 0 else 14 + y_count
            if y_count < 8:
                y_count += 1

            move_mouse_relative(0, y_step)
            time.sleep(0.018)  # 对应 Lua 的 Sleep(18)
    finally:
        with state.lock:
            state.running_loop = False


def run_lock_mouse_loop(state: RuntimeState) -> None:
    with state.lock:
        if state.lock_mouse_running:
            return
        state.lock_mouse_running = True

    try:
        while state.lock_mouse_active:
            current_pos = get_cursor_pos()

            if state.recorded_pos is not None:
                if state.skip_next_correction:
                    state.skip_next_correction = False
                    state.recorded_pos = current_pos
                else:
                    dx = current_pos[0] - state.recorded_pos[0]
                    dy = current_pos[1] - state.recorded_pos[1]
                    distance = (dx * dx + dy * dy) ** 0.5

                    if distance > 15:
                        angle = random.uniform(0, 2 * math.pi)
                        offset_dist = random.uniform(0, 2)
                        target_x = state.recorded_pos[0] + int(offset_dist * math.cos(angle))
                        target_y = state.recorded_pos[1] + int(offset_dist * math.sin(angle))
                        set_cursor_pos(target_x, target_y)
                        state.skip_next_correction = True
                    elif distance > 1:
                        state.recorded_pos = current_pos

            time.sleep(0.016)
    finally:
        with state.lock:
            state.lock_mouse_running = False


def main() -> None:
    state = RuntimeState()
    root = tk.Tk()
    root.title("压枪脚本")
    root.geometry("360x200")
    root.resizable(False, False)

    tip1 = tk.Label(root, text="脚本运行中", font=("Microsoft YaHei UI", 12, "bold"))
    tip1.pack(pady=(15, 5))

    mode_label = tk.Label(root, text="当前模式：压枪模式", font=("Microsoft YaHei UI", 10))
    mode_label.pack(pady=(0, 5))

    def toggle_mode():
        with state.lock:
            if state.mode == "recoil":
                state.mode = "lock"
                mode_label.config(text="当前模式：锁鼠模式")
                btn.config(text="切换为压枪模式")
                tip2.config(text="按住右键激活，点击左键记录位置并锁定")
            else:
                state.mode = "recoil"
                mode_label.config(text="当前模式：压枪模式")
                btn.config(text="切换为锁鼠模式")
                tip2.config(text="按住右键激活，按住左键执行压枪")

    btn = tk.Button(root, text="切换为锁鼠模式", command=toggle_mode, width=20, height=1)
    btn.pack(pady=(0, 5))

    hotkey_var = tk.BooleanVar(value=False)
    hotkey_check = tk.Checkbutton(root, text="启用快捷键切换模式（F6）", variable=hotkey_var, font=("Microsoft YaHei UI", 9))
    hotkey_check.pack(pady=(0, 5))

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
                    can_run = state.recoil_enabled and state.switch_enabled and not state.running_loop and not state.lock_mouse_running

                if current_mode == "recoil":
                    if can_run:
                        t = threading.Thread(target=run_recoil_loop, args=(state,), daemon=True)
                        t.start()
                else:
                    if can_run:
                        state.recorded_pos = get_cursor_pos()
                        state.lock_mouse_active = True
                        t = threading.Thread(target=run_lock_mouse_loop, args=(state,), daemon=True)
                        t.start()
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
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
