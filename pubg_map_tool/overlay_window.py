# -*- coding: utf-8 -*-
"""
游戏覆盖层：地图窗口鼠标穿透；独立拖拽条窗口用于移动位置。
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from PIL import Image, ImageTk

from app_icon import apply_window_icon
from overlay_hotkey import InlineHotkeyCapture, OverlayHotkeyManager
from overlay_settings import DEFAULT_HOTKEY_TOGGLE, load_settings, save_settings
from preview_cache import load_preview_rgba

_SHARED_DIR = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from tool_branding import pack_copyright_ttk  # noqa: E402

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

DRAG_BAR_HEIGHT = 36
DRAG_BAR_BG = "#1e1e2e"
DRAG_BAR_FG = "#89b4fa"

# 控制面板配色（与主程序一致）
UI_BG = "#1e1e2e"
UI_PANEL = "#252536"
UI_TEXT = "#cdd6f4"
UI_MUTED = "#a6adc8"
UI_ACCENT = "#89b4fa"


def _set_click_through(hwnd: int, enabled: bool) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
        style |= WS_EX_LAYERED
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def _window_hwnd(win: tk.Toplevel) -> int:
    import ctypes

    return ctypes.windll.user32.GetParent(win.winfo_id())


class MapOverlayController:
    """地图穿透层 + 可点击拖拽条（双窗口联动）。"""

    OPACITY_MIN, OPACITY_MAX, OPACITY_STEP = 15, 100, 5
    SCALE_MIN, SCALE_MAX, SCALE_STEP = 15, 120, 5

    def __init__(
        self,
        master: tk.Tk,
        data_dir: Path,
        *,
        app_dir: Path | None = None,
        on_closed: Callable[[], None] | None = None,
        on_request_open: Callable[[], None] | None = None,
        on_visibility_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._master = master
        self._data_dir = data_dir
        self._app_dir = app_dir or data_dir.parent
        self._on_closed = on_closed
        self._on_request_open = on_request_open
        self._on_visibility_changed = on_visibility_changed
        self._map_win: tk.Toplevel | None = None
        self._drag_win: tk.Toplevel | None = None
        self._ctrl_win: tk.Toplevel | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._pil_image: Image.Image | None = None
        self._map_path: Path | None = None
        self._map_id: str | None = None
        self._drag_offset: tuple[int, int] | None = None
        self._pos = (100, 100)
        self._map_w = 400
        self._map_h = 400
        self._save_job: str | None = None
        self._hidden = False
        self._last_map_path: Path | None = None
        self._last_map_id: str | None = None
        self._last_title = ""

        # 从磁盘加载配置
        self._settings = load_settings(data_dir)
        self._opacity = self._settings.opacity / 100.0
        self._display_scale = self._settings.scale / 100.0

        self.var_opacity = tk.IntVar(value=self._settings.opacity)
        self.var_scale = tk.IntVar(value=self._settings.scale)
        self.var_topmost = tk.BooleanVar(value=self._settings.topmost)
        self.var_title = tk.StringVar(value="未加载地图")
        self.var_hotkey_enabled = tk.BooleanVar(value=self._settings.hotkey_enabled)
        self.var_hotkey = tk.StringVar(value=self._settings.hotkey_toggle)
        self._ui_sync = False  # 防止滑轨与输入框联动时递归

        self._hotkey_mgr = OverlayHotkeyManager(master, self.toggle_visibility)
        self._reload_hotkey()

    def is_open(self) -> bool:
        return self._map_win is not None and self._map_win.winfo_exists()

    def is_visible(self) -> bool:
        return self.is_open() and not self._hidden

    def shutdown_hotkey(self) -> None:
        """主窗口退出时停止全局热键。"""
        self._hotkey_mgr.stop()

    def _reload_hotkey(self) -> None:
        enabled = bool(self.var_hotkey_enabled.get())
        spec = self.var_hotkey.get().strip() or DEFAULT_HOTKEY_TOGGLE
        self._settings.hotkey_enabled = enabled
        self._settings.hotkey_toggle = spec
        self._hotkey_mgr.apply(enabled, spec)

    def toggle_visibility(self) -> None:
        """全局快捷键：显示 / 隐藏覆盖层（不销毁窗口与配置）。"""
        if self.is_open() and not self._hidden:
            self.hide()
            return
        if self.is_open() and self._hidden:
            self.restore()
            return
        if self._last_map_path and self._last_map_id:
            self.show(self._last_map_path, self._last_title, map_id=self._last_map_id)
            return
        if self._on_request_open:
            self._on_request_open()

    def hide(self) -> None:
        """隐藏覆盖层窗口，保留状态以便快捷键再次唤起。"""
        if not self.is_open() or self._hidden:
            return
        for w in (self._map_win, self._drag_win, self._ctrl_win):
            if w and w.winfo_exists():
                w.withdraw()
        self._hidden = True
        if self._on_visibility_changed:
            self._on_visibility_changed(False)

    def restore(self) -> None:
        """显示已隐藏的覆盖层。"""
        if not self.is_open() or not self._hidden:
            return
        for w in (self._map_win, self._drag_win, self._ctrl_win):
            if w and w.winfo_exists():
                w.deiconify()
        self._hidden = False
        self._apply_topmost()
        if self._on_visibility_changed:
            self._on_visibility_changed(True)

    def show(self, image_path: Path, title: str, *, map_id: str) -> None:
        if not image_path.is_file():
            return
        self._map_path = image_path
        self._map_id = map_id
        self._last_map_path = image_path
        self._last_map_id = map_id
        self._last_title = title
        self.var_title.set(title)

        if not self.is_open():
            self._build_windows()
        else:
            # 再次打开时同步已保存的配置到界面
            self._sync_vars_from_settings()
        self._load_image_async()
        self._hidden = False
        for w in (self._map_win, self._drag_win, self._ctrl_win):
            if w:
                w.deiconify()
        if self._on_visibility_changed:
            self._on_visibility_changed(True)

    def close(self) -> None:
        self._persist_settings()
        for win in (self._map_win, self._drag_win, self._ctrl_win):
            if win and win.winfo_exists():
                win.destroy()
        self._map_win = None
        self._drag_win = None
        self._ctrl_win = None
        self._photo = None
        self._hidden = False
        if self._on_closed:
            self._on_closed()

    def _setup_ctrl_style(self, root: tk.Toplevel) -> ttk.Style:
        """为覆盖层控制面板配置暗色主题（修复 Spinbox 白底白字等问题）。"""
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=UI_BG, foreground=UI_TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("TFrame", background=UI_BG)
        style.configure("Panel.TFrame", background=UI_PANEL)
        style.configure("Panel.TLabelframe", background=UI_PANEL, foreground=UI_ACCENT, bordercolor="#45475a")
        style.configure("Panel.TLabelframe.Label", background=UI_PANEL, foreground=UI_ACCENT)
        style.configure("TLabel", background=UI_BG, foreground=UI_TEXT)
        style.configure("Panel.TLabel", background=UI_PANEL, foreground=UI_TEXT)
        style.configure("Muted.TLabel", background=UI_BG, foreground=UI_MUTED, font=("Microsoft YaHei UI", 8))
        style.configure("MutedPanel.TLabel", background=UI_PANEL, foreground=UI_MUTED, font=("Microsoft YaHei UI", 8))
        style.configure("Title.TLabel", background=UI_BG, foreground=UI_ACCENT, font=("Microsoft YaHei UI", 11, "bold"))
        # 按钮：深色底 + 浅色字
        style.configure(
            "Dark.TButton",
            background=UI_PANEL,
            foreground=UI_TEXT,
            bordercolor="#45475a",
            lightcolor=UI_PANEL,
            darkcolor=UI_PANEL,
            padding=(8, 4),
        )
        style.map(
            "Dark.TButton",
            background=[("active", "#313145"), ("pressed", "#45475a")],
            foreground=[("disabled", UI_MUTED)],
        )
        style.configure("Spin.TButton", padding=(4, 2), width=3)
        # 数值框：深色字段 + 浅色文字（解决截图中的白底白字）
        style.configure(
            "Dark.TSpinbox",
            fieldbackground=UI_PANEL,
            background=UI_PANEL,
            foreground=UI_TEXT,
            arrowcolor=UI_ACCENT,
            bordercolor="#45475a",
            lightcolor=UI_PANEL,
            darkcolor=UI_PANEL,
            insertcolor=UI_TEXT,
        )
        style.map(
            "Dark.TSpinbox",
            fieldbackground=[("readonly", UI_PANEL), ("!disabled", UI_PANEL)],
            foreground=[("readonly", UI_TEXT), ("!disabled", UI_TEXT)],
        )
        # 滑轨：深色槽道
        style.configure(
            "Dark.Horizontal.TScale",
            background=UI_PANEL,
            troughcolor="#3b3b52",
            bordercolor="#45475a",
            lightcolor=UI_PANEL,
            darkcolor=UI_PANEL,
        )
        style.configure(
            "TCheckbutton",
            background=UI_BG,
            foreground=UI_TEXT,
            focuscolor=UI_BG,
        )
        style.map("TCheckbutton", background=[("active", UI_BG)])
        style.configure("Panel.TCheckbutton", background=UI_PANEL, foreground=UI_TEXT)
        style.map("Panel.TCheckbutton", background=[("active", UI_PANEL)])
        root.configure(bg=UI_BG)
        return style

    def _build_windows(self) -> None:
        ctrl = tk.Toplevel(self._master)
        ctrl.title("覆盖层控制")
        ctrl.geometry("380x460")
        ctrl.resizable(False, False)
        ctrl.attributes("-topmost", True)
        ctrl.protocol("WM_DELETE_WINDOW", self.close)
        self._ctrl_win = ctrl
        self._setup_ctrl_style(ctrl)
        apply_window_icon(ctrl, self._app_dir)

        pad = {"padx": 12, "pady": 6}
        ttk.Label(ctrl, textvariable=self.var_title, style="Title.TLabel").pack(anchor="w", **pad)

        panel = ttk.LabelFrame(ctrl, text="显示参数", style="Panel.TLabelframe", padding=(10, 8))
        panel.pack(fill=tk.X, **pad)
        panel_style = "Panel.TLabel"

        self._build_value_row(
            panel,
            "透明度 (%)",
            self.var_opacity,
            self.OPACITY_MIN,
            self.OPACITY_MAX,
            self.OPACITY_STEP,
            self._apply_opacity_from_var,
            label_style=panel_style,
        )
        self._build_value_row(
            panel,
            "显示比例 (%)",
            self.var_scale,
            self.SCALE_MIN,
            self.SCALE_MAX,
            self.SCALE_STEP,
            self._apply_scale_from_var,
            label_style=panel_style,
        )

        ttk.Checkbutton(
            ctrl,
            text="始终置顶",
            variable=self.var_topmost,
            command=self._on_topmost_change,
        ).pack(anchor="w", padx=12, pady=(0, 4))

        hk_panel = ttk.LabelFrame(ctrl, text="快捷键", style="Panel.TLabelframe", padding=(10, 8))
        hk_panel.pack(fill=tk.X, **pad)
        ttk.Checkbutton(
            hk_panel,
            text="启用全局快捷键（显示/隐藏覆盖层）",
            variable=self.var_hotkey_enabled,
            command=self._on_hotkey_enabled_change,
            style="Panel.TCheckbutton",
        ).pack(anchor="w")
        self._hotkey_capture = InlineHotkeyCapture(
            hk_panel,
            self.var_hotkey,
            bg=UI_BG,
            fg=UI_TEXT,
            accent=UI_ACCENT,
            muted=UI_MUTED,
            panel=UI_PANEL,
            on_changed=self._on_hotkey_saved,
            on_capture_start=self._hotkey_mgr.stop,
            on_capture_end=self._reload_hotkey,
        )
        self._hotkey_capture.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            hk_panel,
            text="点击上方区域录入，需包含主键（如 右 Ctrl+M）；Esc 取消",
            style="MutedPanel.TLabel",
            wraplength=320,
        ).pack(anchor="w", pady=(6, 0))
        ttk.Label(
            hk_panel,
            text="隐藏后仍可用同一快捷键唤起（无需重新点「游戏覆盖层」）",
            style="MutedPanel.TLabel",
            wraplength=320,
        ).pack(anchor="w", pady=(2, 0))

        fb = ttk.Frame(ctrl)
        fb.pack(fill=tk.X, padx=12, pady=4)
        ttk.Button(fb, text="居中", style="Dark.TButton", command=self._center_overlay).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(fb, text="关闭覆盖", style="Dark.TButton", command=self.close).pack(side=tk.LEFT)

        ttk.Label(
            ctrl,
            text="地图区域穿透鼠标 · 拖动顶部蓝条移动位置\n所有参数修改后自动保存",
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor="w", padx=12, pady=(4, 4))
        # 覆盖层控制面板底部低调版权标识
        pack_copyright_ttk(ctrl, dark=True, side=tk.BOTTOM, anchor="e", padx=12, pady=(0, 8))

        # 拖拽条
        drag = tk.Toplevel(self._master)
        drag.overrideredirect(True)
        drag.attributes("-topmost", True)
        self._drag_win = drag

        bar = tk.Frame(drag, bg=DRAG_BAR_BG, height=DRAG_BAR_HEIGHT)
        bar.pack(fill=tk.BOTH, expand=True)
        lbl = tk.Label(
            bar,
            text="⠿  按住拖动 · 地图已穿透",
            bg=DRAG_BAR_BG,
            fg=DRAG_BAR_FG,
            font=("Microsoft YaHei UI", 9),
            cursor="fleur",
        )
        lbl.pack(fill=tk.BOTH, expand=True, padx=8)
        for w in (drag, bar, lbl):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_move)
            w.bind("<ButtonRelease-1>", self._on_drag_end)

        map_win = tk.Toplevel(self._master)
        map_win.overrideredirect(True)
        map_win.attributes("-topmost", True)
        self._map_win = map_win
        self._canvas = tk.Canvas(map_win, highlightthickness=0, bg="#010101")
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._apply_topmost()
        self._apply_opacity()
        map_win.after(150, self._enable_map_passthrough)

    def _build_value_row(
        self,
        parent: ttk.Widget,
        label: str,
        var: tk.IntVar,
        min_v: int,
        max_v: int,
        step: int,
        on_apply: Callable[[], None],
        *,
        label_style: str = "TLabel",
    ) -> None:
        """− / 数值 / + 与滑轨组合调节。"""
        block = ttk.Frame(parent, style="Panel.TFrame")
        block.pack(fill=tk.X, pady=(0, 10))

        head = ttk.Frame(block, style="Panel.TFrame")
        head.pack(fill=tk.X)
        ttk.Label(head, text=label, style=label_style).pack(side=tk.LEFT)

        box = ttk.Frame(head, style="Panel.TFrame")
        box.pack(side=tk.RIGHT)

        def clamp(v: int) -> int:
            return max(min_v, min(max_v, int(v)))

        def commit(delta: int = 0, *, from_slider: bool = False) -> None:
            if self._ui_sync:
                return
            self._ui_sync = True
            v = clamp(var.get() + delta)
            var.set(v)
            on_apply()
            self._schedule_save()
            self._ui_sync = False

        ttk.Button(box, text="−", style="Dark.TButton", command=lambda: commit(-step)).pack(side=tk.LEFT)
        entry = tk.Spinbox(
            box,
            from_=min_v,
            to=max_v,
            increment=step,
            textvariable=var,
            width=5,
            justify="center",
            wrap=False,
            bg=UI_PANEL,
            fg=UI_TEXT,
            selectbackground=UI_ACCENT,
            selectforeground=UI_BG,
            buttonbackground=UI_PANEL,
            highlightthickness=1,
            highlightbackground="#45475a",
            highlightcolor=UI_ACCENT,
            readonlybackground=UI_PANEL,
            font=("Consolas", 10),
            command=lambda: commit(0),
        )
        entry.pack(side=tk.LEFT, padx=6)
        entry.bind("<Return>", lambda _e: commit(0))
        entry.bind("<FocusOut>", lambda _e: commit(0))
        ttk.Button(box, text="+", style="Dark.TButton", command=lambda: commit(step)).pack(side=tk.LEFT)

        slider = ttk.Scale(
            block,
            from_=min_v,
            to=max_v,
            orient=tk.HORIZONTAL,
            variable=var,
            style="Dark.Horizontal.TScale",
            command=lambda _v: commit(0, from_slider=True),
        )
        slider.pack(fill=tk.X, pady=(6, 0))

    def _on_hotkey_enabled_change(self) -> None:
        self._settings.hotkey_enabled = self.var_hotkey_enabled.get()
        self._reload_hotkey()
        self._schedule_save()

    def _on_hotkey_saved(self) -> None:
        self._settings.hotkey_toggle = self.var_hotkey.get().strip() or DEFAULT_HOTKEY_TOGGLE
        if hasattr(self, "_hotkey_capture"):
            self._hotkey_capture.refresh()
        self._schedule_save()

    def _sync_vars_from_settings(self) -> None:
        self._ui_sync = True
        self.var_opacity.set(self._settings.opacity)
        self.var_scale.set(self._settings.scale)
        self.var_topmost.set(self._settings.topmost)
        self.var_hotkey_enabled.set(self._settings.hotkey_enabled)
        self.var_hotkey.set(self._settings.hotkey_toggle)
        self._ui_sync = False
        if hasattr(self, "_hotkey_capture"):
            self._hotkey_capture.refresh()
        self._reload_hotkey()
        self._opacity = self._settings.opacity / 100.0
        self._display_scale = self._settings.scale / 100.0
        self._apply_opacity()
        if self._pil_image:
            self._render_image()

    def _apply_opacity_from_var(self) -> None:
        pct = max(self.OPACITY_MIN, min(self.OPACITY_MAX, int(self.var_opacity.get())))
        self.var_opacity.set(pct)
        self._opacity = pct / 100.0
        self._settings.opacity = pct
        self._apply_opacity()

    def _apply_scale_from_var(self) -> None:
        pct = max(self.SCALE_MIN, min(self.SCALE_MAX, int(self.var_scale.get())))
        self.var_scale.set(pct)
        self._display_scale = pct / 100.0
        self._settings.scale = pct
        self._render_image()

    def _on_topmost_change(self) -> None:
        self._settings.topmost = self.var_topmost.get()
        self._apply_topmost()
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._save_job and self._ctrl_win:
            self._ctrl_win.after_cancel(self._save_job)
        if self._ctrl_win:
            self._save_job = self._ctrl_win.after(400, self._persist_settings)

    def _persist_settings(self) -> None:
        self._save_job = None
        self._settings.opacity = max(self.OPACITY_MIN, min(self.OPACITY_MAX, int(self.var_opacity.get())))
        self._settings.scale = max(self.SCALE_MIN, min(self.SCALE_MAX, int(self.var_scale.get())))
        self._settings.topmost = self.var_topmost.get()
        self._settings.hotkey_enabled = self.var_hotkey_enabled.get()
        self._settings.hotkey_toggle = self.var_hotkey.get().strip() or DEFAULT_HOTKEY_TOGGLE
        self._settings.pos_x, self._settings.pos_y = self._pos
        try:
            save_settings(self._data_dir, self._settings)
        except OSError as exc:
            if self._ctrl_win and self._ctrl_win.winfo_exists():
                messagebox.showerror("保存失败", str(exc), parent=self._ctrl_win)

    def _enable_map_passthrough(self) -> None:
        if self._map_win:
            try:
                _set_click_through(_window_hwnd(self._map_win), True)
            except OSError:
                pass

    def _apply_topmost(self) -> None:
        top = self.var_topmost.get()
        for w in (self._map_win, self._drag_win, self._ctrl_win):
            if w:
                w.attributes("-topmost", top)

    def _apply_opacity(self) -> None:
        for w in (self._map_win, self._drag_win):
            if w:
                w.attributes("-alpha", self._opacity)

    def _load_image_async(self) -> None:
        if not self._map_path or not self._map_id:
            return
        path, map_id = self._map_path, self._map_id

        def worker() -> Image.Image:
            return load_preview_rgba(path, map_id, self._data_dir)

        def on_done(result: Image.Image | Exception) -> None:
            if not self.is_open():
                return
            if isinstance(result, Exception):
                return
            self._pil_image = result
            self._render_image()
            if self._settings.pos_x >= 0 and self._settings.pos_y >= 0:
                self._place_at(self._settings.pos_x, self._settings.pos_y)
            else:
                self._center_overlay()

        def run() -> None:
            try:
                img = worker()
                self._master.after(0, lambda: on_done(img))
            except Exception as exc:
                self._master.after(0, lambda: on_done(exc))

        threading.Thread(target=run, daemon=True).start()

    def _render_image(self) -> None:
        if not self._pil_image or not self._map_win or not self._drag_win:
            return
        sw = self._master.winfo_screenwidth()
        sh = self._master.winfo_screenheight()
        target = int(min(sw, sh) * self._display_scale)
        w, h = self._pil_image.size
        ratio = min(target / w, target / h, 1.0)
        self._map_w = max(1, int(w * ratio))
        self._map_h = max(1, int(h * ratio))

        resized = self._pil_image.resize((self._map_w, self._map_h), Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(resized)
        self._canvas.config(width=self._map_w, height=self._map_h)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        self._drag_win.geometry(f"{self._map_w}x{DRAG_BAR_HEIGHT}")
        self._map_win.geometry(f"{self._map_w}x{self._map_h}")
        self._place_at(*self._pos)

    def _place_at(self, x: int, y: int) -> None:
        self._pos = (x, y)
        if self._drag_win:
            self._drag_win.geometry(f"+{x}+{y}")
        if self._map_win:
            self._map_win.geometry(f"+{x}+{y + DRAG_BAR_HEIGHT}")

    def _center_overlay(self) -> None:
        sw = self._master.winfo_screenwidth()
        sh = self._master.winfo_screenheight()
        total_h = self._map_h + DRAG_BAR_HEIGHT
        x = max(0, (sw - self._map_w) // 2)
        y = max(0, (sh - total_h) // 2)
        self._place_at(x, y)
        self._schedule_save()

    def _on_drag_start(self, event: tk.Event) -> None:
        if not self._drag_win:
            return
        self._drag_offset = (event.x_root - self._pos[0], event.y_root - self._pos[1])

    def _on_drag_move(self, event: tk.Event) -> None:
        if self._drag_offset is None:
            return
        ox, oy = self._drag_offset
        self._place_at(event.x_root - ox, event.y_root - oy)

    def _on_drag_end(self, _event: tk.Event) -> None:
        self._drag_offset = None
        self._schedule_save()
