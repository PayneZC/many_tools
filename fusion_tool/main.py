# -*- coding: utf-8 -*-
"""
PUBG 辅助工具：整合 PUBG 地图功能 + 压枪鼠标辅助功能。
"""

from __future__ import annotations

import ctypes
import shutil
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from tkinter import filedialog, messagebox, simpledialog, ttk

# 注释：复用项目内地图模块，压枪配置使用 fusion_tool 自有 recoil_config。
ROOT_DIR = Path(__file__).resolve().parent.parent
PUBG_DIR = ROOT_DIR / "pubg_map_tool"
SHARED_DIR = ROOT_DIR / "shared"
FUSION_DIR = Path(__file__).resolve().parent
for _p in (FUSION_DIR, PUBG_DIR, SHARED_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from PIL import Image, ImageTk
from pynput import mouse

try:
    import pystray
except ImportError:
    pystray = None  # type: ignore[assignment,misc]

from app_icon import apply_window_icon, icon_paths
from tool_branding import pack_copyright_ttk
from persist_paths import app_dir, configure_recoil_config_module, data_dir

configure_recoil_config_module()
from recoil_config import (
    RecoilConfigFile,
    RecoilPreset,
    find_preset,
    load_config,
    move_pixels_for_tick,
    new_preset_id,
    save_config,
)
from app_settings import (
    DEFAULT_MOUSE_HOTKEY,
    AppSettings,
    load_app_settings,
    save_app_settings,
)
from donation_window import DonationWindow
from map_catalog import MapEntry, get_map, iter_maps
from map_fetcher import MapDataStore, download_all_maps, download_single_map
from overlay_hotkey import InlineHotkeyCapture, OverlayHotkeyManager
from overlay_window import MapOverlayController
from preview_cache import load_preview_rgba, prebuild_missing_previews
from single_instance import acquire_single_instance, release_single_instance


APP_DIR = app_dir()
DATA_DIR = data_dir()
# 注释：对外显示名称（窗口标题、托盘、打包 exe 名）。
APP_DISPLAY_NAME = "PUBG辅助工具"
STORE = MapDataStore(DATA_DIR)
STORE.cleanup_legacy_storage()

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
MOUSEEVENTF_MOVE = 0x0001
user32 = ctypes.windll.user32

COLOR_BG = "#1e1e2e"
COLOR_PANEL = "#252536"
COLOR_ACCENT = "#89b4fa"
COLOR_TEXT = "#cdd6f4"
COLOR_MUTED = "#a6adc8"
COLOR_BORDER = "#45475a"


def _dark_entry(master: tk.Widget, textvariable: tk.Variable, *, width: int = 22) -> tk.Entry:
    """注释：暗色输入框，避免 ttk.Entry 在深色主题下白底白字。"""
    return tk.Entry(
        master,
        textvariable=textvariable,
        width=width,
        bg=COLOR_PANEL,
        fg=COLOR_TEXT,
        insertbackground=COLOR_TEXT,
        selectbackground=COLOR_ACCENT,
        selectforeground=COLOR_BG,
        highlightthickness=1,
        highlightbackground=COLOR_BORDER,
        highlightcolor=COLOR_ACCENT,
        font=("Microsoft YaHei UI", 9),
    )


def _dark_spinbox(
    master: tk.Widget,
    textvariable: tk.Variable,
    *,
    from_: int | float,
    to: int | float,
    increment: int | float = 1,
    width: int = 8,
    command: Callable[[], None] | None = None,
) -> tk.Spinbox:
    """注释：暗色数值框，与覆盖层控制面板一致。"""
    w = tk.Spinbox(
        master,
        from_=from_,
        to=to,
        increment=increment,
        textvariable=textvariable,
        width=width,
        justify="center",
        bg=COLOR_PANEL,
        fg=COLOR_TEXT,
        selectbackground=COLOR_ACCENT,
        selectforeground=COLOR_BG,
        buttonbackground=COLOR_PANEL,
        highlightthickness=1,
        highlightbackground=COLOR_BORDER,
        highlightcolor=COLOR_ACCENT,
        readonlybackground=COLOR_PANEL,
        font=("Consolas", 10),
    )
    if command is not None:
        w.configure(command=command)
        w.bind("<Return>", lambda _e: command())
        w.bind("<FocusOut>", lambda _e: command())
    return w


class MapCanvas(tk.Canvas):
    """注释：地图预览画布，提供以鼠标为锚点的缩放、拖拽与自适应显示。"""

    FIT_MARGIN = 0.92
    ZOOM_MIN = 0.12
    ZOOM_MAX = 8.0
    WHEEL_STEP = 1.12

    def __init__(self, master: tk.Widget, **kwargs) -> None:
        super().__init__(master, bg=COLOR_PANEL, highlightthickness=0, **kwargs)
        self._source: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._image_item: int | None = None
        self._zoom = 1.0
        self._offset = (0.0, 0.0)
        self._drag_last: tuple[int, int] | None = None
        self.bind("<Configure>", lambda _e: self._render())
        self.bind("<Enter>", lambda _e: self.focus_set())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._on_wheel_linux(e, zoom_in=True))
        self.bind("<Button-5>", lambda e: self._on_wheel_linux(e, zoom_in=False))
        self.bind("<ButtonPress-1>", self._on_pan_start)
        self.bind("<B1-Motion>", self._on_pan_move)
        self.bind("<ButtonRelease-1>", lambda _e: self._on_pan_end())

    def set_image(self, image: Image.Image | None) -> None:
        self._source = image
        self._zoom = 1.0
        self._center()
        self._render()

    def zoom_by(self, factor: float, *, anchor: tuple[float, float] | None = None) -> None:
        """注释：缩放；未指定锚点时以画布中心为锚点（工具栏按钮）。"""
        if self._source is None:
            return
        cw, ch = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        ax, ay = anchor if anchor else (cw / 2, ch / 2)
        self._apply_zoom(factor, ax, ay)

    def reset_view(self) -> None:
        if self._source is None:
            return
        self._zoom = 1.0
        self._center()
        self._render()

    def _fit_scale(self) -> float:
        """注释：相对原图、适配当前画布的基础比例（不含用户缩放）。"""
        if not self._source:
            return 1.0
        cw, ch = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        w, h = self._source.size
        return min(cw / w, ch / h) * self.FIT_MARGIN

    def _display_size(self) -> tuple[int, int]:
        """注释：当前缩放后图像在画布上的显示宽高。"""
        if not self._source:
            return 1, 1
        w, h = self._source.size
        scale = self._fit_scale() * self._zoom
        return max(1, int(w * scale)), max(1, int(h * scale))

    def _apply_zoom(self, factor: float, mx: float, my: float) -> None:
        """注释：以鼠标位置为锚点缩放，保持指针下的地图点不动。"""
        if not self._source:
            return
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        ox, oy = self._offset
        old_dw, old_dh = self._display_size()
        if old_dw < 1 or old_dh < 1:
            return
        wx = (mx - ox) / old_dw
        wy = (my - oy) / old_dh
        self._zoom = new_zoom
        new_dw, new_dh = self._display_size()
        self._offset = (mx - wx * new_dw, my - wy * new_dh)
        self._render()

    def _on_wheel(self, event: tk.Event) -> None:
        if self._source is None:
            return
        factor = self.WHEEL_STEP if event.delta > 0 else 1.0 / self.WHEEL_STEP
        self._apply_zoom(factor, float(event.x), float(event.y))

    def _on_wheel_linux(self, event: tk.Event, *, zoom_in: bool) -> None:
        if self._source is None:
            return
        factor = self.WHEEL_STEP if zoom_in else 1.0 / self.WHEEL_STEP
        self._apply_zoom(factor, float(event.x), float(event.y))

    def _on_pan_start(self, event: tk.Event) -> None:
        self._drag_last = (event.x, event.y)

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._drag_last is None or self._image_item is None:
            return
        dx = event.x - self._drag_last[0]
        dy = event.y - self._drag_last[1]
        self._drag_last = (event.x, event.y)
        ox, oy = self._offset
        self._offset = (ox + dx, oy + dy)
        self.coords(self._image_item, self._offset[0], self._offset[1])

    def _on_pan_end(self) -> None:
        self._drag_last = None

    def _center(self) -> None:
        if self._source is None:
            return
        cw, ch = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        dw, dh = self._display_size()
        self._offset = ((cw - dw) / 2, (ch - dh) / 2)

    def _render(self) -> None:
        self.delete("all")
        self._image_item = None
        if self._source is None:
            self.create_text(
                max(self.winfo_width(), 1) // 2,
                max(self.winfo_height(), 1) // 2,
                text="请选择地图并更新数据后预览",
                fill=COLOR_MUTED,
            )
            return
        dw, dh = self._display_size()
        resized = self._source.resize((dw, dh), Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(resized)
        self._image_item = self.create_image(self._offset[0], self._offset[1], anchor=tk.NW, image=self._photo)


def is_pressed(vk_code: int) -> bool:
    return (user32.GetAsyncKeyState(vk_code) & 0x8000) != 0


def move_mouse_relative(dx: int, dy: int) -> None:
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


@dataclass
class RuntimeState:
    """注释：压枪运行时状态，供鼠标监听线程共享。"""

    enabled: bool = True
    switch_enabled: bool = False
    running_loop: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    recoil_interval: float = 0.018
    first_move_pixels: int = 28
    increment_base_pixels: int = 14
    increment_times: int = 8
    increment_step_pixels: int = 1


def apply_preset_to_state(state: RuntimeState, preset: RecoilPreset) -> None:
    with state.lock:
        state.recoil_interval = max(0.005, preset.interval_ms / 1000.0)
        state.first_move_pixels = max(1, int(preset.first_move_pixels))
        state.increment_base_pixels = max(0, int(preset.increment_base_pixels))
        state.increment_times = max(1, int(preset.increment_times))
        state.increment_step_pixels = max(0, int(preset.increment_step_pixels))


def run_recoil_loop(state: RuntimeState) -> None:
    """注释：压枪循环，逻辑对齐 Lua：Y_count 从 0 递增并封顶。"""
    with state.lock:
        if state.running_loop:
            return
        state.running_loop = True
    y_count = 0
    try:
        time.sleep(0.001)
        while is_pressed(VK_LBUTTON):
            with state.lock:
                if not (state.enabled and state.switch_enabled):
                    break
                interval = state.recoil_interval
                times = state.increment_times
                move_y = move_pixels_for_tick(
                    y_count,
                    state.first_move_pixels,
                    state.increment_base_pixels,
                    times,
                    state.increment_step_pixels,
                )
            move_mouse_relative(0, move_y)
            if y_count < times:
                y_count += 1
            time.sleep(interval)
    finally:
        with state.lock:
            state.running_loop = False


class FusionToolApp(tk.Tk):
    """注释：整合工具主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_DISPLAY_NAME)
        self.geometry("1240x760")
        self.minsize(1060, 640)
        self.configure(bg=COLOR_BG)
        apply_window_icon(self, APP_DIR)

        self.state = RuntimeState()
        self.config_data: RecoilConfigFile = load_config()
        self._app_settings: AppSettings = load_app_settings()
        self._selected_id: str | None = None
        self._download_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._map_preview_thread: threading.Thread | None = None

        self.listener: mouse.Listener | None = None
        self._editing_preset_id: str | None = None
        self._tray_icon = None
        self._tray_thread: threading.Thread | None = None
        self._is_quitting = False
        self._donation_win: DonationWindow | None = None
        # 注释：全局快捷键切换鼠标辅助总开关（与覆盖层热键共用合并监听）。
        self._mouse_hotkey_mgr = OverlayHotkeyManager(
            self, self._toggle_mouse_by_hotkey, slot="mouse_master"
        )

        self._setup_style()
        self._build_ui()
        self._setup_overlay()
        self._refresh_map_list()
        self._refresh_status_on_boot()
        self._start_preview_prewarm()
        self._start_input_listeners()
        self._reload_mouse_hotkey()
        # 注释：点关闭按钮时最小化到托盘，不直接退出。
        self.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)

    def _setup_style(self) -> None:
        """注释：统一暗色主题，修复表单控件前景/背景对比度不足。"""
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Panel.TFrame", background=COLOR_PANEL)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("Title.TLabel", background=COLOR_BG, font=("Microsoft YaHei UI", 14, "bold"), foreground=COLOR_ACCENT)
        style.configure("Sub.TLabel", background=COLOR_BG, foreground=COLOR_MUTED)
        style.configure(
            "TLabelframe",
            background=COLOR_BG,
            foreground=COLOR_ACCENT,
            bordercolor=COLOR_BORDER,
        )
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_ACCENT, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure(
            "Panel.TLabelframe",
            background=COLOR_PANEL,
            foreground=COLOR_ACCENT,
            bordercolor=COLOR_BORDER,
        )
        style.configure("Panel.TLabelframe.Label", background=COLOR_PANEL, foreground=COLOR_ACCENT)
        style.configure(
            "TNotebook",
            background=COLOR_BG,
            bordercolor=COLOR_BORDER,
            tabmargins=(4, 2, 4, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=COLOR_PANEL,
            foreground=COLOR_MUTED,
            padding=(14, 6),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLOR_BG)],
            foreground=[("selected", COLOR_ACCENT)],
        )
        style.configure(
            "TButton",
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#313145"), ("pressed", "#45475a")],
            foreground=[("disabled", COLOR_MUTED)],
        )
        style.configure("Accent.TButton", background=COLOR_ACCENT, foreground=COLOR_BG)
        style.map("Accent.TButton", background=[("active", "#74c7ec"), ("pressed", "#5a9fd4")])
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLOR_PANEL,
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            arrowcolor=COLOR_ACCENT,
            bordercolor=COLOR_BORDER,
            insertcolor=COLOR_TEXT,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", COLOR_PANEL), ("!disabled", COLOR_PANEL)],
            foreground=[("readonly", COLOR_TEXT), ("!disabled", COLOR_TEXT)],
        )
        style.configure(
            "TCheckbutton",
            background=COLOR_BG,
            foreground=COLOR_TEXT,
            focuscolor=COLOR_BG,
        )
        style.configure("Panel.TCheckbutton", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.map("TCheckbutton", background=[("active", COLOR_BG)])
        style.map("Panel.TCheckbutton", background=[("active", COLOR_PANEL)])
        style.configure(
            "TRadiobutton",
            background=COLOR_BG,
            foreground=COLOR_TEXT,
            focuscolor=COLOR_BG,
        )
        style.map("TRadiobutton", background=[("active", COLOR_BG)])
        style.configure(
            "Dark.Horizontal.TScale",
            background=COLOR_PANEL,
            troughcolor="#3b3b52",
            bordercolor=COLOR_BORDER,
        )
        style.configure("Treeview", background=COLOR_PANEL, fieldbackground=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("Treeview.Heading", background=COLOR_PANEL, foreground=COLOR_ACCENT)
        style.configure(
            "Horizontal.TProgressbar",
            background=COLOR_ACCENT,
            troughcolor=COLOR_PANEL,
            bordercolor=COLOR_BORDER,
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text=APP_DISPLAY_NAME, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="打赏", command=self._open_donation_window).pack(side=tk.RIGHT, padx=(8, 0))

        self.tabs = ttk.Notebook(container)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        self.map_tab = ttk.Frame(self.tabs)
        self.mouse_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.map_tab, text="地图工具")
        self.tabs.add(self.mouse_tab, text="鼠标辅助")

        self._build_map_tab()
        self._build_mouse_tab()

        self.var_status = tk.StringVar(value="就绪")
        status_bar = ttk.Frame(container)
        status_bar.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(status_bar, textvariable=self.var_status, style="Sub.TLabel").pack(side=tk.LEFT)
        # 状态栏右侧低调版权标识（与各小工具统一）
        pack_copyright_ttk(status_bar, dark=True)
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=180)
        self.progress.pack(side=tk.RIGHT)

    def _setup_overlay(self) -> None:
        self._overlay = MapOverlayController(
            self,
            DATA_DIR,
            app_dir=APP_DIR,
            on_closed=lambda: self._set_status("覆盖层已关闭"),
            on_request_open=self._open_overlay,
            on_visibility_changed=lambda visible: self._set_status("覆盖层已显示" if visible else "覆盖层已隐藏"),
        )

    def _build_map_tab(self) -> None:
        body = ttk.Panedwindow(self.map_tab, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = ttk.Frame(body, style="Panel.TFrame", padding=8)
        body.add(left, weight=1)
        ttk.Label(left, text="地图列表（pubg.im）", style="Panel.TLabel").pack(anchor="w", pady=(0, 6))
        self.tree = ttk.Treeview(left, columns=("name", "status", "updated"), show="headings", selectmode="browse")
        self.tree.heading("name", text="地图")
        self.tree.heading("status", text="8x8")
        self.tree.heading("updated", text="更新时间")
        self.tree.column("name", width=160)
        self.tree.column("status", width=60, anchor=tk.CENTER)
        self.tree.column("updated", width=130, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_map)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        ops = ttk.LabelFrame(left, text="地图数据操作", style="Panel.TLabelframe", padding=8)
        ops.pack(fill=tk.X, pady=(8, 0))
        row = ttk.Frame(ops)
        row.pack(fill=tk.X)
        ttk.Button(row, text="更新全部", style="Accent.TButton", command=self._update_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="更新当前", command=self._update_current).pack(side=tk.LEFT, padx=(0, 6))
        self.btn_cancel = ttk.Button(row, text="取消下载", command=self._cancel_download, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT)

        right = ttk.Frame(body, padding=8)
        body.add(right, weight=3)
        toolbar = ttk.LabelFrame(right, text="预览操作", padding=8)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="放大", command=lambda: self.canvas.zoom_by(1.2)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="缩小", command=lambda: self.canvas.zoom_by(1 / 1.2)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="适配窗口", command=self.canvas_reset).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="导出PNG", command=self._export_map).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="游戏覆盖层", command=self._open_overlay).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="滚轮缩放 · 左键拖拽 · 双击地图名打开覆盖层", style="Sub.TLabel").pack(side=tk.LEFT, padx=(12, 0))
        self.canvas = MapCanvas(right)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _build_mouse_tab(self) -> None:
        frame = ttk.Frame(self.mouse_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text="压枪鼠标辅助", style="Title.TLabel").pack(side=tk.LEFT)
        self.mouse_status = tk.StringVar(value="● 运行中")
        ttk.Label(top, textvariable=self.mouse_status, style="Sub.TLabel").pack(side=tk.RIGHT)

        self.var_mouse_enabled = tk.BooleanVar(value=True)
        master_row = ttk.Frame(frame)
        master_row.pack(fill=tk.X, anchor=tk.W, pady=(0, 6))
        ttk.Checkbutton(
            master_row,
            text="启用鼠标功能（总开关）",
            variable=self.var_mouse_enabled,
            command=self._on_mouse_master_toggle,
        ).pack(side=tk.LEFT)
        self.var_mouse_hotkey_enabled = tk.BooleanVar(value=self._app_settings.mouse_hotkey_enabled)
        ttk.Checkbutton(
            master_row,
            text="快捷键",
            variable=self.var_mouse_hotkey_enabled,
            command=self._on_mouse_hotkey_enabled_change,
        ).pack(side=tk.LEFT, padx=(14, 4))
        self.var_mouse_hotkey = tk.StringVar(value=self._app_settings.mouse_hotkey_toggle)
        self._mouse_hotkey_capture = InlineHotkeyCapture(
            master_row,
            self.var_mouse_hotkey,
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            accent=COLOR_ACCENT,
            muted=COLOR_MUTED,
            panel=COLOR_PANEL,
            compact=True,
            on_changed=self._on_mouse_hotkey_saved,
            on_capture_start=self._mouse_hotkey_mgr.stop,
            on_capture_end=self._reload_mouse_hotkey,
        )
        self._mouse_hotkey_capture.pack(side=tk.LEFT)

        ttk.Label(
            frame,
            text="按住右键激活 · 按住左键压枪 · 双击方案可设为当前",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        body = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        list_panel = ttk.LabelFrame(body, text="方案列表", padding=8)
        body.add(list_panel, weight=2)
        cols = ("active", "name", "interval", "first", "base", "times", "step")
        self.preset_tree = ttk.Treeview(list_panel, columns=cols, show="headings", selectmode="browse", height=12)
        self.preset_tree.heading("active", text="当前")
        self.preset_tree.heading("name", text="方案名")
        self.preset_tree.heading("interval", text="间隔ms")
        self.preset_tree.heading("first", text="首次")
        self.preset_tree.heading("base", text="基数")
        self.preset_tree.heading("times", text="次数")
        self.preset_tree.heading("step", text="步长")
        self.preset_tree.column("active", width=40, anchor=tk.CENTER)
        self.preset_tree.column("name", width=96, stretch=True)
        self.preset_tree.column("interval", width=52, anchor=tk.CENTER)
        self.preset_tree.column("first", width=40, anchor=tk.CENTER)
        self.preset_tree.column("base", width=40, anchor=tk.CENTER)
        self.preset_tree.column("times", width=40, anchor=tk.CENTER)
        self.preset_tree.column("step", width=40, anchor=tk.CENTER)
        self.preset_tree.pack(fill=tk.BOTH, expand=True)
        self.preset_tree.bind("<<TreeviewSelect>>", self._on_preset_list_select)
        self.preset_tree.bind("<Double-1>", self._on_preset_list_double_click)

        list_btns = ttk.Frame(list_panel)
        list_btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(list_btns, text="新建", command=self._on_new_preset).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(list_btns, text="删除", command=self._on_delete_preset).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(list_btns, text="设为当前", command=self._on_set_active_preset).pack(side=tk.LEFT)

        detail_panel = ttk.LabelFrame(body, text="方案编辑", padding=10)
        body.add(detail_panel, weight=3)

        self.name_var = tk.StringVar()
        self.interval_var = tk.DoubleVar(value=18.0)
        self.first_move_var = tk.IntVar(value=28)
        self.increment_base_var = tk.IntVar(value=14)
        self.increment_times_var = tk.IntVar(value=8)
        self.increment_step_var = tk.IntVar(value=1)
        self.hz_hint = tk.StringVar(value="约 55.6 次/秒")
        self.move_preview = tk.StringVar(value="")

        form = ttk.Frame(detail_panel)
        form.pack(fill=tk.BOTH, expand=True, anchor=tk.NW)
        form.columnconfigure(1, weight=1)

        def _form_field(
            row: int,
            title: str,
            hint: str,
            build_widget: Callable[[ttk.Frame], tk.Widget],
            *,
            build_extra: Callable[[ttk.Frame], tk.Widget] | None = None,
        ) -> int:
            """注释：控件 parent 必须为 line，避免 grid/pack 错位。"""
            ttk.Label(form, text=title, width=11).grid(row=row, column=0, sticky=tk.NW, pady=(8, 0), padx=(0, 8))
            cell = ttk.Frame(form)
            cell.grid(row=row, column=1, sticky=tk.W, pady=(8, 0))
            line = ttk.Frame(cell)
            line.pack(anchor=tk.W)
            build_widget(line).pack(side=tk.LEFT)
            if build_extra is not None:
                build_extra(line).pack(side=tk.LEFT, padx=(10, 0))
            ttk.Label(cell, text=hint, style="Sub.TLabel", wraplength=280).pack(anchor=tk.W, pady=(2, 0))
            return row + 1

        row = 0
        ttk.Label(form, text="方案名称", width=11).grid(row=row, column=0, sticky=tk.W, pady=8, padx=(0, 8))
        _dark_entry(form, self.name_var, width=24).grid(row=row, column=1, sticky=tk.EW, pady=8)
        row += 1

        row = _form_field(
            row,
            "压枪间隔",
            "每次下移之间的等待时间",
            lambda p: _dark_spinbox(p, self.interval_var, from_=5, to=200, increment=1, command=self._sync_runtime_from_ui),
            build_extra=lambda p: ttk.Label(p, textvariable=self.hz_hint, style="Sub.TLabel"),
        )
        row = _form_field(
            row,
            "首次移动",
            "第一次下移的距离",
            lambda p: _dark_spinbox(p, self.first_move_var, from_=1, to=120, command=self._sync_runtime_from_ui),
        )
        row = _form_field(
            row,
            "递增基数",
            "之后每次移动的距离",
            lambda p: _dark_spinbox(p, self.increment_base_var, from_=0, to=120, command=self._sync_runtime_from_ui),
        )
        row = _form_field(
            row,
            "递增次数",
            "递增计数的最大次数",
            lambda p: _dark_spinbox(p, self.increment_times_var, from_=1, to=30, command=self._sync_runtime_from_ui),
        )
        row = _form_field(
            row,
            "递增距离",
            "每次递增增加的距离",
            lambda p: _dark_spinbox(p, self.increment_step_var, from_=0, to=80, command=self._sync_runtime_from_ui),
        )

        ttk.Label(form, textvariable=self.move_preview, style="Sub.TLabel", wraplength=320).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(8, 8)
        )
        row += 1

        action_row = ttk.Frame(form)
        action_row.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        ttk.Button(action_row, text="保存方案", style="Accent.TButton", command=self._on_save_preset).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_row, text="放弃修改", command=self._on_revert_preset_edit).pack(side=tk.LEFT)

        self.interval_var.trace_add("write", lambda *_: self._sync_runtime_from_ui())
        self.first_move_var.trace_add("write", lambda *_: self._sync_runtime_from_ui())
        self.increment_base_var.trace_add("write", lambda *_: self._sync_runtime_from_ui())
        self.increment_times_var.trace_add("write", lambda *_: self._sync_runtime_from_ui())
        self.increment_step_var.trace_add("write", lambda *_: self._sync_runtime_from_ui())

        self._refresh_preset_list()
        active = find_preset(self.config_data, self.config_data.active_preset_id) or self.config_data.presets[0]
        self._select_preset_in_list(active.id)
        self._load_preset_to_ui(active)

    def _refresh_status_on_boot(self) -> None:
        manifest = STORE.load_manifest()
        if manifest.maps:
            self._set_status(f"已加载 {len(manifest.maps)} 张本地地图")
        else:
            self._set_status("尚未下载地图，请先点击「更新全部」")

    def _start_preview_prewarm(self) -> None:
        # 注释：后台预热地图预览缓存，避免首次切图卡顿。
        paths = {entry.id: STORE.image_path(entry.id) for entry in iter_maps()}
        threading.Thread(target=lambda: prebuild_missing_previews(DATA_DIR, paths), daemon=True).start()

    def _set_status(self, text: str) -> None:
        self.var_status.set(text)

    def canvas_reset(self) -> None:
        self.canvas.reset_view()

    def _refresh_map_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        manifest = STORE.load_manifest()
        record_by_id = {m.id: m for m in (manifest.maps or [])}
        for entry in iter_maps():
            rec = record_by_id.get(entry.id)
            downloaded = STORE.image_path(entry.id).is_file()
            status_8x8 = "✓" if (rec and rec.with_8x8) or (entry.has_detailed and manifest.with_8x8) else "-"
            if not entry.has_detailed:
                status_8x8 = "—"
            updated = (rec.updated_at[:10] if rec else "-") if downloaded else "未下载"
            self.tree.insert("", tk.END, iid=entry.id, values=(entry.display_name, status_8x8, updated))

    def _on_select_map(self, _event: tk.Event | None = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self._selected_id = sel[0]
        self._load_map_preview(sel[0])

    def _load_map_preview(self, map_id: str) -> None:
        path = STORE.image_path(map_id)
        if not path.is_file():
            self.canvas.set_image(None)
            return

        def worker() -> None:
            try:
                img = load_preview_rgba(path, map_id, DATA_DIR)
            except Exception:
                self.after(0, lambda: self.canvas.set_image(None))
                return
            self.after(0, lambda: self.canvas.set_image(img))

        self._map_preview_thread = threading.Thread(target=worker, daemon=True)
        self._map_preview_thread.start()
        entry = get_map(map_id)
        if entry:
            self._set_status(f"已加载: {entry.display_name}")

    def _on_tree_double_click(self, event: tk.Event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        self._selected_id = row_id
        self._open_overlay()

    def _get_selected_entry(self) -> MapEntry | None:
        if not self._selected_id:
            messagebox.showinfo("提示", "请先在左侧选择一张地图。")
            return None
        return get_map(self._selected_id)

    def _set_downloading(self, downloading: bool) -> None:
        if downloading:
            self.progress.start(12)
            self.btn_cancel.config(state=tk.NORMAL)
        else:
            self.progress.stop()
            self.btn_cancel.config(state=tk.DISABLED)

    def _cancel_download(self) -> None:
        self._cancel_event.set()
        self._set_status("正在取消下载…")

    def _download_worker(self, fn, on_done) -> None:
        if self._download_thread and self._download_thread.is_alive():
            messagebox.showwarning("提示", "已有下载任务在进行中。")
            return
        self._cancel_event.clear()
        self._set_downloading(True)

        def run() -> None:
            try:
                fn()
            finally:
                self.after(0, lambda: (self._set_downloading(False), on_done()))

        self._download_thread = threading.Thread(target=run, daemon=True)
        self._download_thread.start()

    def _on_download_progress(self, map_id: str, message: str) -> None:
        def update() -> None:
            if map_id:
                entry = get_map(map_id)
                name = entry.display_name if entry else map_id
                self._set_status(f"[{name}] {message}")
            else:
                self._set_status(message)
        self.after(0, update)

    def _update_all(self) -> None:
        if not messagebox.askyesno("更新全部地图", "将从 pubg.im 下载全部地图，是否继续？"):
            return

        def work() -> None:
            download_all_maps(
                STORE,
                with_8x8=True,
                on_progress=self._on_download_progress,
                cancel_event=self._cancel_event,
            )

        def done() -> None:
            self._refresh_map_list()
            self._on_select_map()
            self._set_status("全部地图更新完成")

        self._download_worker(work, done)

    def _update_current(self) -> None:
        entry = self._get_selected_entry()
        if not entry:
            return

        def work() -> None:
            rec = download_single_map(entry, STORE, with_8x8=True, on_progress=self._on_download_progress)
            manifest = STORE.load_manifest()
            maps = {m.id: m for m in (manifest.maps or [])}
            maps[rec.id] = rec
            from map_fetcher import Manifest
            STORE.save_manifest(Manifest(with_8x8=True, updated_at=rec.updated_at, maps=list(maps.values())))

        def done() -> None:
            self._refresh_map_list()
            self._on_select_map()
            self._set_status(f"已更新: {entry.display_name}")

        self._download_worker(work, done)

    def _export_map(self) -> None:
        entry = self._get_selected_entry()
        if not entry:
            return
        src = STORE.image_path(entry.id)
        if not src.is_file():
            messagebox.showwarning("提示", "当前地图尚未下载。")
            return
        dest = filedialog.asksaveasfilename(
            title="导出地图",
            defaultextension=".png",
            initialfile=f"{entry.id}_8x8.png",
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")],
        )
        if not dest:
            return
        shutil.copy2(src, dest)
        self._set_status(f"已导出到: {dest}")

    def _open_overlay(self) -> None:
        entry = self._get_selected_entry()
        if not entry:
            return
        path = STORE.image_path(entry.id)
        if not path.is_file():
            if messagebox.askyesno("提示", "当前地图未下载，是否先下载？"):
                self._update_current()
            return
        self._overlay.show(path, entry.display_name, map_id=entry.id)
        self._set_status(f"覆盖层已打开: {entry.display_name}")

    def _selected_preset_id(self) -> str | None:
        sel = self.preset_tree.selection()
        return sel[0] if sel else None

    def _selected_preset(self) -> RecoilPreset | None:
        pid = self._selected_preset_id()
        return find_preset(self.config_data, pid) if pid else None

    def _refresh_preset_list(self) -> None:
        for item in self.preset_tree.get_children():
            self.preset_tree.delete(item)
        active_id = self.config_data.active_preset_id
        for preset in self.config_data.presets:
            mark = "●" if preset.id == active_id else ""
            self.preset_tree.insert(
                "",
                tk.END,
                iid=preset.id,
                values=(
                    mark,
                    preset.name,
                    f"{preset.interval_ms:.0f}",
                    preset.first_move_pixels,
                    preset.increment_base_pixels,
                    preset.increment_times,
                    preset.increment_step_pixels,
                ),
            )

    def _select_preset_in_list(self, preset_id: str) -> None:
        if self.preset_tree.exists(preset_id):
            self.preset_tree.selection_set(preset_id)
            self.preset_tree.focus(preset_id)
            self._editing_preset_id = preset_id

    def _load_preset_to_ui(self, preset: RecoilPreset) -> None:
        self._editing_preset_id = preset.id
        self.name_var.set(preset.name)
        self.interval_var.set(preset.interval_ms)
        self.first_move_var.set(preset.first_move_pixels)
        self.increment_base_var.set(preset.increment_base_pixels)
        self.increment_times_var.set(preset.increment_times)
        self.increment_step_var.set(preset.increment_step_pixels)
        if preset.id == self.config_data.active_preset_id:
            apply_preset_to_state(self.state, preset)
        self._update_hz_hint()
        self._update_move_preview()

    def _update_hz_hint(self) -> None:
        ms = max(1.0, self.interval_var.get())
        self.hz_hint.set(f"约 {1000.0 / ms:.1f} 次/秒")

    def _update_move_preview(self) -> None:
        first_px = int(self.first_move_var.get())
        base_px = int(self.increment_base_var.get())
        times = int(self.increment_times_var.get())
        step_px = int(self.increment_step_var.get())
        steps = [
            move_pixels_for_tick(i, first_px, base_px, times, step_px)
            for i in range(min(6, times + 2))
        ]
        seq = " → ".join(str(s) for s in steps)
        cap = move_pixels_for_tick(times + 5, first_px, base_px, times, step_px)
        self.move_preview.set(f"下移序列：{seq} … 达次数上限后 {cap}px")

    def _sync_runtime_from_ui(self) -> None:
        # 注释：仅当前启用方案参与实时压枪，避免编辑其他方案时误改运行时参数。
        if self._editing_preset_id == self.config_data.active_preset_id:
            apply_preset_to_state(
                self.state,
                RecoilPreset(
                    id=self._editing_preset_id,
                    name=self.name_var.get().strip() or "未命名",
                    interval_ms=float(self.interval_var.get()),
                    first_move_pixels=int(self.first_move_var.get()),
                    increment_base_pixels=int(self.increment_base_var.get()),
                    increment_times=int(self.increment_times_var.get()),
                    increment_step_pixels=int(self.increment_step_var.get()),
                ),
            )
        self._update_hz_hint()
        self._update_move_preview()

    def _on_preset_list_select(self, _event: tk.Event | None = None) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        self._load_preset_to_ui(preset)

    def _on_preset_list_double_click(self, event: tk.Event) -> None:
        """注释：双击方案行设为当前启用方案。"""
        if self.preset_tree.identify_region(event.x, event.y) != "cell":
            return
        row_id = self.preset_tree.identify_row(event.y)
        if not row_id:
            return
        self.preset_tree.selection_set(row_id)
        self.preset_tree.focus(row_id)
        self._on_set_active_preset()

    def _on_set_active_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            messagebox.showinfo("提示", "请先在列表中选择一个方案。")
            return
        self.config_data.active_preset_id = preset.id
        save_config(self.config_data)
        apply_preset_to_state(self.state, preset)
        self._refresh_preset_list()
        self._select_preset_in_list(preset.id)
        self._set_status(f"当前方案：{preset.name}")

    def _on_revert_preset_edit(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        self._load_preset_to_ui(preset)

    def _on_new_preset(self) -> None:
        default_name = f"方案{len(self.config_data.presets) + 1}"
        raw_name = simpledialog.askstring("新建方案", "请输入方案名称：", initialvalue=default_name, parent=self)
        if raw_name is None:
            return
        name = raw_name.strip()
        if not name:
            messagebox.showwarning("名称无效", "方案名称不能为空。", parent=self)
            return
        preset = RecoilPreset(
            new_preset_id(),
            name,
            interval_ms=float(self.interval_var.get()),
            first_move_pixels=int(self.first_move_var.get()),
            increment_base_pixels=int(self.increment_base_var.get()),
            increment_times=int(self.increment_times_var.get()),
            increment_step_pixels=int(self.increment_step_var.get()),
        )
        self.config_data.presets.append(preset)
        self.config_data.active_preset_id = preset.id
        save_config(self.config_data)
        self._refresh_preset_list()
        self._select_preset_in_list(preset.id)
        self._load_preset_to_ui(preset)
        apply_preset_to_state(self.state, preset)

    def _on_save_preset(self) -> None:
        preset = self._selected_preset()
        name = self.name_var.get().strip() or "未命名"
        interval_ms = float(self.interval_var.get())
        first_move = int(self.first_move_var.get())
        increment_base = int(self.increment_base_var.get())
        increment_times = int(self.increment_times_var.get())
        increment_step = int(self.increment_step_var.get())
        if interval_ms < 5:
            messagebox.showwarning("参数无效", "压枪间隔不能小于 5 毫秒。")
            return
        if first_move < 1:
            messagebox.showwarning("参数无效", "首次移动距离不能小于 1 像素。")
            return
        if increment_base < 0:
            messagebox.showwarning("参数无效", "递增基数不能为负数。")
            return
        if increment_times < 1:
            messagebox.showwarning("参数无效", "递增次数至少为 1。")
            return
        if increment_step < 0:
            messagebox.showwarning("参数无效", "递增距离不能为负数。")
            return
        if preset is None:
            preset = RecoilPreset(
                new_preset_id(),
                name,
                interval_ms,
                first_move,
                increment_base,
                increment_times,
                increment_step,
            )
            self.config_data.presets.append(preset)
        else:
            preset.name = name
            preset.interval_ms = interval_ms
            preset.first_move_pixels = first_move
            preset.increment_base_pixels = increment_base
            preset.increment_times = increment_times
            preset.increment_step_pixels = increment_step
        save_config(self.config_data)
        self._refresh_preset_list()
        self._select_preset_in_list(preset.id)
        if preset.id == self.config_data.active_preset_id:
            apply_preset_to_state(self.state, preset)
        messagebox.showinfo("已保存", f"方案「{name}」已保存。")

    def _on_delete_preset(self) -> None:
        if len(self.config_data.presets) <= 1:
            messagebox.showwarning("无法删除", "至少保留一条压枪方案。")
            return
        preset = self._selected_preset()
        if preset is None:
            return
        if not messagebox.askyesno("确认删除", f"确定删除方案「{preset.name}」吗？"):
            return
        self.config_data.presets = [p for p in self.config_data.presets if p.id != preset.id]
        if self.config_data.active_preset_id == preset.id:
            self.config_data.active_preset_id = self.config_data.presets[0].id
        save_config(self.config_data)
        self._refresh_preset_list()
        active = find_preset(self.config_data, self.config_data.active_preset_id) or self.config_data.presets[0]
        apply_preset_to_state(self.state, active)
        self._select_preset_in_list(active.id)
        self._load_preset_to_ui(active)

    def _on_mouse_master_toggle(self) -> None:
        enabled = self.var_mouse_enabled.get()
        with self.state.lock:
            self.state.enabled = enabled
            if not enabled:
                self.state.switch_enabled = False
        self.mouse_status.set("● 运行中" if enabled else "● 已暂停")
        self._set_status("鼠标辅助已启用" if enabled else "鼠标辅助已暂停")

    def _toggle_mouse_by_hotkey(self) -> None:
        """注释：全局快捷键回调，切换鼠标辅助总开关。"""
        self.var_mouse_enabled.set(not self.var_mouse_enabled.get())
        self._on_mouse_master_toggle()

    def _reload_mouse_hotkey(self) -> None:
        """注释：应用已保存的鼠标辅助快捷键配置。"""
        enabled = bool(self.var_mouse_hotkey_enabled.get())
        spec = self.var_mouse_hotkey.get().strip() or DEFAULT_MOUSE_HOTKEY
        self._app_settings.mouse_hotkey_enabled = enabled
        self._app_settings.mouse_hotkey_toggle = spec
        ok = self._mouse_hotkey_mgr.apply(enabled, spec)
        if hasattr(self, "_mouse_hotkey_capture"):
            self._mouse_hotkey_capture.refresh()
        if enabled and not ok:
            self._set_status("鼠标快捷键注册失败，请更换组合键")

    def _on_mouse_hotkey_enabled_change(self) -> None:
        self._app_settings.mouse_hotkey_enabled = self.var_mouse_hotkey_enabled.get()
        self._reload_mouse_hotkey()
        save_app_settings(self._app_settings)

    def _on_mouse_hotkey_saved(self) -> None:
        self._app_settings.mouse_hotkey_toggle = self.var_mouse_hotkey.get().strip() or DEFAULT_MOUSE_HOTKEY
        save_app_settings(self._app_settings)
        self._reload_mouse_hotkey()

    def _open_donation_window(self) -> None:
        """注释：打开打赏窗口展示收款码。"""
        if self._donation_win is not None and self._donation_win.winfo_exists():
            self._donation_win.lift()
            self._donation_win.focus_force()
            return
        self._donation_win = DonationWindow(self)

    def _get_tray_image(self) -> Image.Image:
        """注释：托盘图标，优先使用应用图标。"""
        icon_png, icon_ico = icon_paths(FUSION_DIR)
        if icon_png.is_file():
            img = Image.open(icon_png).convert("RGBA")
        elif icon_ico.is_file():
            img = Image.open(icon_ico).convert("RGBA")
        else:
            img = Image.new("RGBA", (64, 64), (137, 180, 250, 255))
        # 注释：Windows 托盘对尺寸敏感，统一缩放到 64x64。
        if img.size != (64, 64):
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
        return img

    def _run_tray_icon_loop(self) -> None:
        """注释：在后台线程运行托盘消息循环。"""
        if self._tray_icon is not None:
            self._tray_icon.run()

    def _create_tray_icon(self) -> bool:
        """注释：创建系统托盘图标与右键菜单。"""
        if pystray is None:
            self._set_status("托盘不可用：请执行 pip install pystray")
            return False
        if self._tray_icon is not None:
            return True
        try:
            image = self._get_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("显示界面", self._tray_on_show, default=True),
                pystray.MenuItem("打赏", self._tray_on_donation),
                pystray.MenuItem("退出", self._tray_on_exit),
            )
            self._tray_icon = pystray.Icon("pubg_assist_tool", image, APP_DISPLAY_NAME, menu)
            started = False
            if hasattr(self._tray_icon, "run_detached"):
                try:
                    self._tray_icon.run_detached()
                    started = True
                except Exception:
                    started = False
            if not started:
                if self._tray_thread is None or not self._tray_thread.is_alive():
                    self._tray_thread = threading.Thread(
                        target=self._run_tray_icon_loop,
                        name="fusion_tray",
                        daemon=True,
                    )
                    self._tray_thread.start()
            return True
        except Exception as exc:
            self._tray_icon = None
            self._set_status(f"托盘初始化失败：{exc}")
            return False

    def _tray_on_show(self, _icon=None, _item=None) -> None:
        self.after(0, self._restore_from_tray)

    def _tray_on_donation(self, _icon=None, _item=None) -> None:
        self.after(0, self._open_donation_window)

    def _tray_on_exit(self, _icon=None, _item=None) -> None:
        self.after(0, self._quit_application)

    def _on_close_to_tray(self) -> None:
        """注释：关闭主窗口时隐藏到托盘。"""
        if not self._create_tray_icon():
            messagebox.showerror(
                "托盘不可用",
                "无法创建系统托盘图标。\n请安装依赖：pip install pystray pillow\n\n"
                "若已安装仍失败，请从任务栏「^」展开隐藏图标区域查看。",
                parent=self,
            )
            return
        self.withdraw()
        self.update_idletasks()
        self._set_status("已最小化到系统托盘，可在右下角托盘区恢复")

    def _restore_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self._set_status("已恢复主窗口")

    def _stop_tray_icon(self) -> None:
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _quit_application(self) -> None:
        """注释：真正退出：停止监听、热键与托盘。"""
        if self._is_quitting:
            return
        self._is_quitting = True
        if self.listener is not None:
            self.listener.stop()
        self._mouse_hotkey_mgr.stop()
        self._overlay.shutdown_hotkey()
        self._stop_tray_icon()
        self.destroy()

    def _start_input_listeners(self) -> None:
        # 注释：右键激活、左键压枪，参数来自当前方案运行时状态。
        def on_click(_x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
            with self.state.lock:
                if not self.state.enabled:
                    return
            if button == mouse.Button.right:
                with self.state.lock:
                    self.state.switch_enabled = pressed
                return
            if button == mouse.Button.left and pressed:
                with self.state.lock:
                    can_run = (
                        self.state.enabled
                        and self.state.switch_enabled
                        and not self.state.running_loop
                    )
                if can_run:
                    threading.Thread(target=run_recoil_loop, args=(self.state,), daemon=True).start()

        self.listener = mouse.Listener(on_click=on_click)
        self.listener.start()

def main() -> None:
    # 注释：仅允许单实例运行。
    mutex = acquire_single_instance()
    if mutex == 0:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("提示", f"{APP_DISPLAY_NAME}已在运行中，请勿重复启动。")
        root.destroy()
        return
    try:
        app = FusionToolApp()
        app.mainloop()
    finally:
        release_single_instance(mutex)


if __name__ == "__main__":
    main()
