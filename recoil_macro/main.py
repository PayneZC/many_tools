"""
Windows 压枪宏（Logitech Lua 脚本的 Python 实现）。

与 Lua 脚本对应的功能：
1) 按住鼠标右键（button 2）时启用压枪开关。
2) 在开关生效时，按住鼠标左键持续向下移动鼠标。
3) 跟随模式：按住右键激活，按住左键跟踪屏幕中心目标。
"""

from __future__ import annotations

import ctypes
import importlib.util
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

_SHARED_DIR = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from tool_branding import pack_copyright  # noqa: E402


def _app_dir() -> Path:
    """脚本目录；打包后为 exe 所在目录（配置写入同级）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_APP_DIR = _app_dir()
# 依赖清单使用项目根目录 requirements.txt（与其他工具一致）
_REQUIREMENTS_FILE = _APP_DIR.parent / "requirements.txt" if not getattr(sys, "frozen", False) else _APP_DIR / "requirements.txt"

_RUNTIME_MODULES = (
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("PIL", "pillow"),
    ("pynput", "pynput"),
)


def _missing_modules() -> list[tuple[str, str]]:
    """返回缺失的 (模块名, pip 包名) 列表。"""
    missing: list[tuple[str, str]] = []
    for mod_name, pip_name in _RUNTIME_MODULES:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append((mod_name, pip_name))
    return missing


def _try_install_dependencies() -> bool:
    """使用当前解释器自动安装 requirements.txt。"""
    if not _REQUIREMENTS_FILE.is_file():
        return False
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(_REQUIREMENTS_FILE)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        return proc.returncode == 0 and not _missing_modules()
    except (OSError, subprocess.SubprocessError):
        return False


def _show_dependency_dialog(title: str, message: str, ask_install: bool) -> bool:
    """弹窗提示；若 ask_install 为 True 则询问是否自动安装。"""
    try:
        root = tk.Tk()
        root.withdraw()
        if ask_install:
            do_install = messagebox.askyesno(title, message)
        else:
            messagebox.showerror(title, message)
            do_install = False
        root.destroy()
        return do_install
    except Exception:
        print(message, file=sys.stderr)
        return False


def _ensure_runtime_dependencies() -> None:
    """启动前检查第三方库；可尝试自动安装，失败则给出明确指引。"""
    # 打包 exe 已内置依赖，无需 pip 检查
    if getattr(sys, "frozen", False):
        return
    if not _missing_modules():
        return

    py_path = sys.executable
    req_hint = str(_REQUIREMENTS_FILE)
    missing_pkgs = " ".join(pkg for _, pkg in _missing_modules())

    prompt = (
        f"缺少运行依赖：{missing_pkgs}\n\n"
        f"当前 Python：\n{py_path}\n\n"
        "是否现在自动安装？（需要联网）"
    )
    if _show_dependency_dialog("压枪脚本 - 依赖缺失", prompt, ask_install=True):
        if _try_install_dependencies():
            return
        fail_msg = (
            "自动安装失败。\n\n"
            f"请手动在命令行执行：\n"
            f'  "{py_path}" -m pip install -r "{req_hint}"\n\n'
            "若提示找不到 python，请使用 Miniconda 或运行 build_exe.bat 生成 exe。"
        )
        _show_dependency_dialog("压枪脚本 - 安装失败", fail_msg, ask_install=False)
        raise SystemExit(1)

    manual_msg = (
        f"缺少运行依赖：{missing_pkgs}\n\n"
        f"当前 Python：\n{py_path}\n\n"
        "请任选一种方式安装：\n"
        f'1) 在项目根目录执行："{py_path}" -m pip install -r requirements.txt\n'
        f'2) 或打包为 exe：recoil_macro\\build_exe.bat'
    )
    _show_dependency_dialog("压枪脚本 - 依赖缺失", manual_msg, ask_install=False)
    raise SystemExit(1)


_ensure_runtime_dependencies()

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
    from .config import (
        CONFIG_PATH,
        RecoilConfigFile,
        RecoilPreset,
        find_preset,
        load_config,
        new_preset_id,
        save_config,
    )
except ImportError:
    from follow_core import (
        RobustPointTracker,
        TRACK_REGION_HALF,
        TrackerConfig,
        to_gray,
    )
    from config import (
        CONFIG_PATH,
        RecoilConfigFile,
        RecoilPreset,
        find_preset,
        load_config,
        new_preset_id,
        save_config,
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
    # 压枪参数（可由界面方案同步）
    recoil_interval: float = 0.018
    recoil_move_pixels: int = 14


def apply_preset_to_state(state: RuntimeState, preset: RecoilPreset) -> None:
    """将方案参数写入运行时状态。"""
    with state.lock:
        state.recoil_interval = max(0.005, preset.interval_ms / 1000.0)
        state.recoil_move_pixels = max(1, int(preset.move_pixels))


def run_recoil_loop(state: RuntimeState) -> None:
    with state.lock:
        if state.running_loop:
            return
        state.running_loop = True

    try:
        time.sleep(0.001)
        while is_pressed(VK_LBUTTON):
            with state.lock:
                if not (state.recoil_enabled and state.switch_enabled):
                    break
                interval = state.recoil_interval
                move_y = state.recoil_move_pixels

            move_mouse_relative(0, move_y)
            time.sleep(interval)
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


def _setup_style(root: tk.Tk) -> ttk.Style:
    """统一界面字体与间距。"""
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure(".", font=("Microsoft YaHei UI", 9))
    style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
    style.configure("Subtitle.TLabel", font=("Microsoft YaHei UI", 9), foreground="#555555")
    style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9, "bold"), foreground="#1a7f37")
    style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 9, "bold"))
    style.configure("Hint.TLabel", font=("Microsoft YaHei UI", 8), foreground="#777777")
    return style


def main() -> None:
    state = RuntimeState()
    config_data = load_config()

    root = tk.Tk()
    root.title("压枪 / 鼠标辅助")
    # 默认高度按「选项展开 + 底部提示」预留，避免展开后底部被裁切
    root.geometry("440x620")
    root.minsize(420, 480)
    _setup_style(root)

    container = ttk.Frame(root, padding=12)
    container.pack(fill=tk.BOTH, expand=True)

    header = ttk.Frame(container)
    header.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(header, text="压枪 / 鼠标辅助", style="Title.TLabel").pack(side=tk.LEFT)
    status_label = ttk.Label(header, text="● 运行中", style="Status.TLabel")
    status_label.pack(side=tk.RIGHT)

    mode_var = tk.StringVar(value="recoil")
    mode_badge = ttk.Label(container, text="当前模式：压枪模式", style="Subtitle.TLabel")
    mode_badge.pack(anchor=tk.W, pady=(0, 6))

    tip2 = ttk.Label(
        container,
        text="按住右键激活，按住左键执行压枪",
        style="Subtitle.TLabel",
        wraplength=400,
    )
    tip2.pack(anchor=tk.W, pady=(0, 8))

    mode_frame = ttk.LabelFrame(container, text="工作模式", padding=10)
    mode_frame.pack(fill=tk.X, pady=(0, 8))

    def refresh_mode_ui() -> None:
        is_recoil = mode_var.get() == "recoil"
        with state.lock:
            state.mode = "recoil" if is_recoil else "lock"
        mode_badge.config(text=f"当前模式：{'压枪模式' if is_recoil else '跟随模式'}")
        tip2.config(
            text="按住右键激活，按住左键执行压枪"
            if is_recoil
            else "按住右键激活，按住左键跟随目标区域"
        )
        if is_recoil:
            recoil_panel.pack(fill=tk.X, pady=(0, 8))
            follow_panel.pack_forget()
        else:
            recoil_panel.pack_forget()
            follow_panel.pack(fill=tk.X, pady=(0, 8))

    ttk.Radiobutton(
        mode_frame, text="压枪模式", value="recoil", variable=mode_var, command=refresh_mode_ui
    ).grid(row=0, column=0, sticky=tk.W, padx=(0, 16))
    ttk.Radiobutton(
        mode_frame, text="跟随模式", value="lock", variable=mode_var, command=refresh_mode_ui
    ).grid(row=0, column=1, sticky=tk.W)

    # —— 压枪参数与多方案 ——
    recoil_panel = ttk.LabelFrame(container, text="压枪参数", padding=10)
    preset_label_to_id: dict[str, str] = {}
    name_var = tk.StringVar()
    interval_var = tk.DoubleVar(value=18.0)
    move_var = tk.IntVar(value=14)
    hz_hint = tk.StringVar(value="约 55.6 次/秒")

    def _preset_label(preset: RecoilPreset) -> str:
        return f"{preset.name}  ({preset.interval_ms:.0f}ms / {preset.move_pixels}px)"

    def _selected_preset() -> RecoilPreset | None:
        pid = preset_label_to_id.get(preset_combo.get(), "")
        return find_preset(config_data, pid)

    def _select_preset_in_combo(preset: RecoilPreset) -> None:
        preset_combo.set(_preset_label(preset))
        config_data.active_preset_id = preset.id

    def _refresh_preset_combo() -> None:
        preset_label_to_id.clear()
        labels: list[str] = []
        for preset in config_data.presets:
            label = _preset_label(preset)
            labels.append(label)
            preset_label_to_id[label] = preset.id
        preset_combo["values"] = labels
        active = find_preset(config_data, config_data.active_preset_id) or config_data.presets[0]
        _select_preset_in_combo(active)

    def _load_preset_to_ui(preset: RecoilPreset) -> None:
        name_var.set(preset.name)
        interval_var.set(preset.interval_ms)
        move_var.set(preset.move_pixels)
        apply_preset_to_state(state, preset)
        _update_hz_hint()

    def _update_hz_hint() -> None:
        ms = max(1.0, interval_var.get())
        hz_hint.set(f"约 {1000.0 / ms:.1f} 次/秒")

    def _sync_runtime_from_ui() -> None:
        pid = preset_label_to_id.get(preset_combo.get(), "tmp")
        apply_preset_to_state(
            state,
            RecoilPreset(
                id=pid,
                name=name_var.get().strip() or "未命名",
                interval_ms=float(interval_var.get()),
                move_pixels=int(move_var.get()),
            ),
        )
        _update_hz_hint()

    def on_preset_selected(_event: object | None = None) -> None:
        preset = _selected_preset()
        if preset is None:
            return
        config_data.active_preset_id = preset.id
        _load_preset_to_ui(preset)

    def on_param_change(*_args: object) -> None:
        _sync_runtime_from_ui()

    def on_save_preset() -> None:
        preset = _selected_preset()
        name = name_var.get().strip() or "未命名"
        interval_ms = float(interval_var.get())
        move_pixels = int(move_var.get())
        if interval_ms < 5:
            messagebox.showwarning("参数无效", "压枪间隔不能小于 5 毫秒。")
            return
        if move_pixels < 1:
            messagebox.showwarning("参数无效", "移动距离不能小于 1 像素。")
            return

        if preset is None:
            preset = RecoilPreset(new_preset_id(), name, interval_ms, move_pixels)
            config_data.presets.append(preset)
            config_data.active_preset_id = preset.id
        else:
            preset.name = name
            preset.interval_ms = interval_ms
            preset.move_pixels = move_pixels

        save_config(config_data)
        _refresh_preset_combo()
        _select_preset_in_combo(preset)
        messagebox.showinfo("已保存", f"方案「{name}」已写入配置文件。")

    def on_new_preset() -> None:
        # 弹出对话框让用户自定义方案名称，取消则不创建
        default_name = f"方案{len(config_data.presets) + 1}"
        raw_name = simpledialog.askstring(
            "新建方案",
            "请输入方案名称：",
            initialvalue=default_name,
            parent=root,
        )
        if raw_name is None:
            return
        name = raw_name.strip()
        if not name:
            messagebox.showwarning("名称无效", "方案名称不能为空。", parent=root)
            return
        if any(p.name == name for p in config_data.presets):
            if not messagebox.askyesno(
                "名称重复",
                f"已存在名为「{name}」的方案，仍要创建吗？",
                parent=root,
            ):
                return

        preset = RecoilPreset(
            new_preset_id(),
            name,
            interval_ms=float(interval_var.get()),
            move_pixels=int(move_var.get()),
        )
        config_data.presets.append(preset)
        config_data.active_preset_id = preset.id
        save_config(config_data)
        _refresh_preset_combo()
        _select_preset_in_combo(preset)
        _load_preset_to_ui(preset)

    def on_delete_preset() -> None:
        if len(config_data.presets) <= 1:
            messagebox.showwarning("无法删除", "至少保留一条压枪方案。")
            return
        preset = _selected_preset()
        if preset is None:
            return
        if not messagebox.askyesno("确认删除", f"确定删除方案「{preset.name}」吗？"):
            return
        config_data.presets = [p for p in config_data.presets if p.id != preset.id]
        config_data.active_preset_id = config_data.presets[0].id
        save_config(config_data)
        _refresh_preset_combo()
        on_preset_selected()

    recoil_panel.columnconfigure(1, weight=1)

    ttk.Label(recoil_panel, text="配置方案").grid(row=0, column=0, sticky=tk.W, pady=2)
    preset_row = ttk.Frame(recoil_panel)
    preset_row.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=2)
    preset_row.columnconfigure(0, weight=1)
    preset_combo = ttk.Combobox(preset_row, state="readonly", width=28)
    preset_combo.grid(row=0, column=0, sticky=tk.EW)
    preset_combo.bind("<<ComboboxSelected>>", on_preset_selected)

    btn_row = ttk.Frame(recoil_panel)
    btn_row.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(4, 8))
    ttk.Button(btn_row, text="新建方案", command=on_new_preset, width=10).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_row, text="保存方案", command=on_save_preset, width=10).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_row, text="删除方案", command=on_delete_preset, width=10).pack(side=tk.LEFT)

    ttk.Label(recoil_panel, text="方案名称").grid(row=2, column=0, sticky=tk.W, pady=2)
    ttk.Entry(recoil_panel, textvariable=name_var, width=24).grid(
        row=2, column=1, columnspan=2, sticky=tk.EW, pady=2
    )

    ttk.Label(recoil_panel, text="移动距离").grid(row=3, column=0, sticky=tk.W, pady=2)
    move_spin = ttk.Spinbox(
        recoil_panel, from_=1, to=80, textvariable=move_var, width=8, command=on_param_change
    )
    move_spin.grid(row=3, column=1, sticky=tk.W, pady=2)
    ttk.Label(recoil_panel, text="像素 / 次", style="Hint.TLabel").grid(row=3, column=2, sticky=tk.W)

    ttk.Label(recoil_panel, text="压枪间隔").grid(row=4, column=0, sticky=tk.W, pady=2)
    interval_spin = ttk.Spinbox(
        recoil_panel,
        from_=5,
        to=200,
        increment=1,
        textvariable=interval_var,
        width=8,
        command=on_param_change,
    )
    interval_spin.grid(row=4, column=1, sticky=tk.W, pady=2)
    ttk.Label(recoil_panel, textvariable=hz_hint, style="Hint.TLabel").grid(row=4, column=2, sticky=tk.W)

    cfg_hint = ttk.Label(
        recoil_panel,
        text=f"配置保存位置：{CONFIG_PATH}",
        style="Hint.TLabel",
        wraplength=380,
    )
    cfg_hint.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))

    interval_var.trace_add("write", on_param_change)
    move_var.trace_add("write", on_param_change)

    # —— 跟随参数 ——
    follow_panel = ttk.LabelFrame(container, text="跟随参数", padding=10)
    follow_panel.columnconfigure(1, weight=1)
    ttk.Label(follow_panel, text="跟随灵敏度").grid(row=0, column=0, sticky=tk.W, pady=4)

    def on_sensitivity_change(val: str) -> None:
        state.sensitivity = float(val)

    sens_var = tk.DoubleVar(value=0.8)
    sens_scale = ttk.Scale(
        follow_panel,
        from_=0.1,
        to=2.0,
        variable=sens_var,
        orient=tk.HORIZONTAL,
        command=on_sensitivity_change,
    )
    sens_scale.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=4)
    sens_value_label = ttk.Label(follow_panel, text="0.8")
    sens_value_label.grid(row=0, column=2, padx=(8, 0))

    def _update_sens_label(*_args: object) -> None:
        sens_value_label.config(text=f"{sens_var.get():.1f}")

    sens_var.trace_add("write", _update_sens_label)

    # 可折叠「选项」区（用 Frame 而非空 LabelFrame，避免标题栏占位导致按钮偏下）
    options_section = ttk.Frame(container)
    options_collapsed = tk.BooleanVar(value=True)

    def _options_toggle_label() -> str:
        return f"{'▶' if options_collapsed.get() else '▼'}  选项"

    def _fit_window_to_content() -> None:
        """按当前布局自适应窗口高度，展开/收起选项后保证底部提示完整可见。"""
        root.update_idletasks()
        min_w, min_h = root.minsize()
        w = max(root.winfo_width(), min_w)
        h = max(root.winfo_reqheight(), min_h)
        root.geometry(f"{w}x{h}")

    def _toggle_options_section() -> None:
        if options_collapsed.get():
            options_body.pack(fill=tk.X, padx=4, pady=(2, 0))
            options_collapsed.set(False)
        else:
            options_body.pack_forget()
            options_collapsed.set(True)
        options_toggle_btn.config(text=_options_toggle_label())
        _fit_window_to_content()

    options_header = ttk.Frame(options_section)
    options_header.pack(fill=tk.X, pady=0)
    options_toggle_btn = ttk.Button(
        options_header,
        text=_options_toggle_label(),
        command=_toggle_options_section,
        style="Toolbutton",
    )
    options_toggle_btn.pack(anchor=tk.W, pady=0)

    options_body = ttk.Frame(options_section)
    hotkey_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(options_body, text="启用快捷键切换模式（F6）", variable=hotkey_var).pack(
        anchor=tk.W, pady=(0, 2)
    )

    debug_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(options_body, text="显示跟随调试窗口", variable=debug_var).pack(anchor=tk.W, pady=2)
    preview_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(options_body, text="调试窗口显示锁定框预览", variable=preview_var).pack(
        anchor=tk.W, pady=2
    )
    game_mode_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        options_body, text="游戏兼容模式（自动最小化 / 禁用预览）", variable=game_mode_var
    ).pack(anchor=tk.W, pady=(2, 0))

    footer_hint = ttk.Label(container, text="关闭此窗口将退出程序", style="Hint.TLabel")

    # 初始化方案列表与默认参数
    _refresh_preset_combo()
    active = find_preset(config_data, config_data.active_preset_id) or config_data.presets[0]
    _load_preset_to_ui(active)
    refresh_mode_ui()
    options_section.pack(fill=tk.X, pady=(4, 4))
    footer_hint.pack(anchor=tk.W, pady=(2, 0))
    # 窗口底部低调版权标识
    pack_copyright(container, fill=tk.X)
    _fit_window_to_content()

    def on_hotkey_toggle_mode() -> None:
        mode_var.set("lock" if mode_var.get() == "recoil" else "recoil")
        refresh_mode_ui()

    def on_hotkey_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        try:
            if key == keyboard.Key.f6:
                with state.lock:
                    enabled = state.hotkey_enabled
                if enabled:
                    root.after(0, on_hotkey_toggle_mode)
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
