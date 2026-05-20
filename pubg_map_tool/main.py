# -*- coding: utf-8 -*-
"""
PUBG 地图工具 — 从 pubg.im/maps 同步 8x8 带点地图，支持查看、导出与游戏覆盖层。

数据源：https://pubg.im/maps （开启 8x8 地图细节后的资源）
"""

from __future__ import annotations

import shutil
import sys
import threading

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from app_icon import apply_window_icon
from map_catalog import MapEntry, get_map, iter_maps
from map_fetcher import MapDataStore, download_all_maps, download_single_map
from overlay_window import MapOverlayController
from preview_cache import load_preview_rgba, prebuild_missing_previews

_SHARED_DIR = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from tool_branding import pack_copyright_ttk  # noqa: E402

# 注册 AVIF 解码
try:
    import pillow_avif  # noqa: F401
except ImportError:
    pass


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
DATA_DIR = APP_DIR / "data"
STORE = MapDataStore(DATA_DIR)
STORE.cleanup_legacy_storage()

# 界面配色
COLOR_BG = "#1e1e2e"
COLOR_PANEL = "#252536"
COLOR_ACCENT = "#89b4fa"
COLOR_TEXT = "#cdd6f4"
COLOR_MUTED = "#a6adc8"
FONT_UI = ("Microsoft YaHei UI", 10)
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")


class MapCanvas(tk.Canvas):
    """
    地图预览：多级分辨率缓存 + 后台重采样，滚轮缩放更流畅。
    """

    FIT_MARGIN = 0.92
    ZOOM_REL_MIN = 0.12
    ZOOM_REL_MAX = 8.0
    WHEEL_STEP = 1.12
    RENDER_DEBOUNCE_MS = 45
    # 预览金字塔各级最长边（加载后后台生成）
    PYRAMID_EDGES = (384, 768, 1152, 1536, 2048)
    VIEWPORT_PIXEL_CAP = 2.5  # 显示像素不超过视口最长边的倍数

    def __init__(self, master, data_dir: Path, **kwargs) -> None:
        super().__init__(master, highlightthickness=0, bg=COLOR_PANEL, **kwargs)
        self._data_dir = data_dir
        self._source: Image.Image | None = None
        self._pil_pyramid: dict[tuple[int, int], Image.Image] = {}
        self._photo: ImageTk.PhotoImage | None = None
        self._image_item: int | None = None
        self._placeholder_item: int | None = None
        self._loading_item: int | None = None
        self._zoom_factor = 1.0
        self._offset = (0.0, 0.0)
        self._drag_last: tuple[int, int] | None = None
        self._load_generation = 0
        self._fit_retry = 0
        self._last_fit_size: tuple[int, int] = (0, 0)
        self._render_job: str | None = None
        self._render_gen = 0
        self._want_hq_after_zoom = False

        self.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Enter>", lambda _e: self.focus_set())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._on_wheel_linux(e, zoom_in=True))
        self.bind("<Button-5>", lambda e: self._on_wheel_linux(e, zoom_in=False))
        self.bind("<ButtonPress-1>", self._on_pan_start)
        self.bind("<B1-Motion>", self._on_pan_move)
        self.bind("<ButtonRelease-1>", self._on_pan_end)

    def set_image(self, path: Path | None, map_id: str | None = None) -> None:
        """异步加载地图；map_id 用于预览缓存路径。"""
        self._load_generation += 1
        gen = self._load_generation
        self._clear_image_item()
        self._source = None
        self._photo = None
        self._zoom_factor = 1.0
        self._offset = (0.0, 0.0)
        self._fit_retry = 0

        if not path or not path.is_file() or not map_id:
            self._hide_loading()
            self._show_placeholder()
            return

        self._show_loading()

        def worker() -> Image.Image:
            return load_preview_rgba(path, map_id, self._data_dir)

        def on_done(result: Image.Image | Exception) -> None:
            if gen != self._load_generation:
                return
            if isinstance(result, Exception):
                self._hide_loading()
                self._show_placeholder(f"加载失败: {result}")
                return
            self._hide_loading()
            self._mount_image(result)

        def run_in_background() -> None:
            try:
                img = worker()
                self.after(0, lambda: on_done(img))
            except Exception as exc:
                self.after(0, lambda: on_done(exc))

        threading.Thread(target=run_in_background, daemon=True).start()

    def zoom_by(self, factor: float, *, anchor: tuple[float, float] | None = None) -> None:
        if self._image_item is None:
            return
        cx = self.winfo_width() / 2
        cy = self.winfo_height() / 2
        ax, ay = anchor if anchor else (cx, cy)
        self._apply_zoom(factor, ax, ay)

    def reset_view(self) -> None:
        if self._source is None:
            return
        self._apply_fit_view()

    def _clear_image_item(self) -> None:
        if self._image_item is not None:
            self.delete(self._image_item)
            self._image_item = None

    def _show_placeholder(self, text: str | None = None) -> None:
        if self._placeholder_item is not None:
            self.delete(self._placeholder_item)
        cw, ch = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        msg = text or "请选择左侧地图，或点击「更新全部地图」下载数据\n滚轮缩放 · 左键拖拽平移"
        self._placeholder_item = self.create_text(
            cw // 2,
            ch // 2,
            text=msg,
            fill=COLOR_MUTED,
            font=FONT_UI,
            justify=tk.CENTER,
        )

    def _show_loading(self) -> None:
        if self._placeholder_item is not None:
            self.delete(self._placeholder_item)
            self._placeholder_item = None
        self._hide_loading()
        cw, ch = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        self._loading_item = self.create_text(
            cw // 2,
            ch // 2,
            text="正在加载地图预览…",
            fill=COLOR_ACCENT,
            font=FONT_UI,
        )

    def _hide_loading(self) -> None:
        if self._loading_item is not None:
            self.delete(self._loading_item)
            self._loading_item = None

    def _mount_image(self, image: Image.Image) -> None:
        self._source = image
        self._pil_pyramid = {(image.width, image.height): image}
        if self._placeholder_item is not None:
            self.delete(self._placeholder_item)
            self._placeholder_item = None
        self._zoom_factor = 1.0
        self._fit_retry = 0
        gen = self._load_generation
        threading.Thread(target=self._build_pyramid_async, args=(image.copy(), gen), daemon=True).start()
        self.after_idle(self._apply_fit_view)

    def _build_pyramid_async(self, image: Image.Image, gen: int) -> None:
        """后台构建多级 PIL 缓存，缩短缩放时重采样时间。"""
        w, h = image.size
        pyramid: dict[tuple[int, int], Image.Image] = {(w, h): image}
        for edge in self.PYRAMID_EDGES:
            if max(w, h) <= edge:
                continue
            ratio = edge / max(w, h)
            nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
            if (nw, nh) in pyramid:
                continue
            pyramid[(nw, nh)] = image.resize((nw, nh), Image.Resampling.BILINEAR)

        def apply() -> None:
            if gen != self._load_generation:
                return
            self._pil_pyramid = pyramid

        self.after(0, apply)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if event.width < 80 or not self._source:
            return
        if abs(self._zoom_factor - 1.0) > 0.01:
            return
        size = (event.width, event.height)
        if size == self._last_fit_size:
            return
        self._last_fit_size = size
        self._apply_fit_view()

    def _fit_scale(self) -> float:
        """相对原图、适配当前画布宽高的比例。"""
        if not self._source:
            return 1.0
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        w, h = self._source.size
        return min(cw / w, ch / h) * self.FIT_MARGIN

    def _display_size(self) -> tuple[int, int]:
        assert self._source is not None
        w, h = self._source.size
        s = self._fit_scale() * self._zoom_factor
        dw, dh = max(1, int(w * s)), max(1, int(h * s))
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        cap = int(max(cw, ch) * self.VIEWPORT_PIXEL_CAP)
        if dw > cap or dh > cap:
            r = min(cap / dw, cap / dh)
            dw, dh = max(1, int(dw * r)), max(1, int(dh * r))
        return dw, dh

    def _resize_for_display(self, dw: int, dh: int, *, hq: bool) -> Image.Image:
        """从金字塔选最近的一级再缩放到目标尺寸。"""
        assert self._source is not None
        resample = Image.Resampling.BILINEAR if hq else Image.Resampling.NEAREST
        best_key: tuple[int, int] | None = None
        best_area = -1
        largest_key: tuple[int, int] | None = None
        largest_area = -1
        target_area = dw * dh
        for (pw, ph) in self._pil_pyramid:
            area = pw * ph
            if area > largest_area:
                largest_area = area
                largest_key = (pw, ph)
            if area >= target_area and (best_key is None or area < best_area):
                best_key = (pw, ph)
                best_area = area
        if best_key is None:
            best_key = largest_key
        base = self._pil_pyramid.get(best_key, self._source) if best_key else self._source
        if base.size == (dw, dh):
            return base
        if dw < base.width and dh < base.height and not hq:
            out = base.copy()
            out.thumbnail((dw, dh), resample)
            return out
        return base.resize((dw, dh), resample)

    def _center_offset(self) -> None:
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        dw, dh = self._display_size()
        self._offset = ((cw - dw) / 2, (ch - dh) / 2)

    def _apply_fit_view(self) -> None:
        if not self._source:
            return
        self.update_idletasks()
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        if (cw < 120 or ch < 120) and self._fit_retry < 12:
            self._fit_retry += 1
            self.after(50, self._apply_fit_view)
            return
        self._zoom_factor = 1.0
        self._center_offset()
        self._last_fit_size = (cw, ch)
        self._redisplay_now(hq=True)

    def _apply_photo(self, pil: Image.Image, ox: float, oy: float) -> None:
        self._photo = ImageTk.PhotoImage(pil)
        if self._image_item is None:
            self._image_item = self.create_image(ox, oy, anchor=tk.NW, image=self._photo)
        else:
            self.itemconfig(self._image_item, image=self._photo)
            self.coords(self._image_item, ox, oy)

    def _redisplay_now(self, *, hq: bool) -> None:
        if not self._source:
            return
        dw, dh = self._display_size()
        ox, oy = self._offset
        display = self._resize_for_display(dw, dh, hq=hq)
        self._apply_photo(display, ox, oy)

    def _schedule_redisplay(self, *, hq_after: bool = False) -> None:
        if hq_after:
            self._want_hq_after_zoom = True
        if self._render_job:
            self.after_cancel(self._render_job)

        def run() -> None:
            self._render_job = None
            self._start_bg_render(fast=not self._want_hq_after_zoom)
            if self._want_hq_after_zoom:
                self._want_hq_after_zoom = False
                self._render_job = self.after(120, self._hq_pass)

        self._render_job = self.after(self.RENDER_DEBOUNCE_MS, run)

    def _hq_pass(self) -> None:
        self._render_job = None
        self._start_bg_render(fast=False)

    def _start_bg_render(self, *, fast: bool) -> None:
        if not self._source:
            return
        self._render_gen += 1
        gen = self._render_gen
        dw, dh = self._display_size()
        ox, oy = self._offset
        hq = not fast

        def worker() -> tuple[int, Image.Image, float, float]:
            pil = self._resize_for_display(dw, dh, hq=hq)
            return gen, pil, ox, oy

        def on_done(result: tuple[int, Image.Image, float, float]) -> None:
            g, pil, x, y = result
            if g != self._render_gen or not self._source:
                return
            self._apply_photo(pil, x, y)

        def run_thread() -> None:
            try:
                payload = worker()
            except Exception:
                return
            self.after(0, lambda: on_done(payload))

        threading.Thread(target=run_thread, daemon=True).start()

    def _apply_zoom(self, factor: float, mx: float, my: float) -> None:
        if not self._source:
            return
        new_zoom = self._zoom_factor * factor
        if new_zoom < self.ZOOM_REL_MIN or new_zoom > self.ZOOM_REL_MAX:
            return
        ox, oy = self._offset
        old_dw, old_dh = self._display_size()
        if old_dw < 1 or old_dh < 1:
            return
        # 以鼠标位置为锚点，缩放后保持该点对准同一地图位置
        wx = (mx - ox) / old_dw
        wy = (my - oy) / old_dh
        self._zoom_factor = new_zoom
        new_dw, new_dh = self._display_size()
        self._offset = (mx - wx * new_dw, my - wy * new_dh)
        self._schedule_redisplay(hq_after=True)

    def _on_wheel(self, event: tk.Event) -> None:
        if self._image_item is None:
            return
        factor = self.WHEEL_STEP if event.delta > 0 else 1.0 / self.WHEEL_STEP
        self._apply_zoom(factor, float(event.x), float(event.y))

    def _on_wheel_linux(self, event: tk.Event, *, zoom_in: bool) -> None:
        if self._image_item is None:
            return
        factor = self.WHEEL_STEP if zoom_in else 1.0 / self.WHEEL_STEP
        self._apply_zoom(factor, float(event.x), float(event.y))

    def _on_pan_start(self, event: tk.Event) -> None:
        self._drag_last = (event.x, event.y)

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._drag_last is None or self._image_item is None:
            return
        lx, ly = self._drag_last
        dx, dy = event.x - lx, event.y - ly
        self._drag_last = (event.x, event.y)
        ox, oy = self._offset
        self._offset = (ox + dx, oy + dy)
        self.coords(self._image_item, self._offset[0], self._offset[1])

    def _on_pan_end(self, _event: tk.Event) -> None:
        self._drag_last = None


class PubgMapApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PUBG 地图工具")
        self.geometry("1180x720")
        self.minsize(960, 600)
        self.configure(bg=COLOR_BG)

        self._selected_id: str | None = None
        self._download_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._overlay = MapOverlayController(
            self,
            DATA_DIR,
            app_dir=APP_DIR,
            on_closed=self._on_overlay_closed,
            on_request_open=self._open_overlay,
            on_visibility_changed=self._on_overlay_visibility,
        )
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

        apply_window_icon(self, APP_DIR)
        self._setup_style()
        self._build_ui()
        self._refresh_map_list()

        manifest = STORE.load_manifest()
        if manifest.maps:
            self._set_status(f"已加载 {len(manifest.maps)} 张本地地图（8x8: {'开' if manifest.with_8x8 else '关'}）")
        else:
            self._set_status("尚未下载地图，请点击「更新全部地图」从 pubg.im 同步")

        # 后台预生成 JPEG 预览，加速后续切换（不阻塞界面）
        self._start_preview_prewarm()

    def _start_preview_prewarm(self) -> None:
        paths = {entry.id: STORE.image_path(entry.id) for entry in iter_maps()}

        def work() -> None:
            prebuild_missing_previews(DATA_DIR, paths)

        threading.Thread(target=work, daemon=True).start()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_UI)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Panel.TFrame", background=COLOR_PANEL)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="#1e1e2e")
        style.map("Accent.TButton", background=[("active", "#74c7ec"), ("pressed", "#5a9fd4")])
        style.configure("Treeview", background=COLOR_PANEL, fieldbackground=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("Treeview.Heading", background=COLOR_PANEL, foreground=COLOR_ACCENT)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(16, 12, 16, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="PUBG 地图工具", font=FONT_TITLE, foreground=COLOR_ACCENT).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="数据源: pubg.im/maps · 8x8 坐标地图",
            foreground=COLOR_MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, padx=(12, 0))

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        # 左侧列表
        left = ttk.Frame(body, style="Panel.TFrame", padding=8)
        body.add(left, weight=1)

        ttk.Label(left, text="地图列表", style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        columns = ("name", "status", "updated")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", height=20, selectmode="browse")
        self.tree.heading("name", text="地图")
        self.tree.heading("status", text="8x8")
        self.tree.heading("updated", text="更新时间")
        self.tree.column("name", width=140, stretch=True)
        self.tree.column("status", width=50, anchor=tk.CENTER)
        self.tree.column("updated", width=120, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_map)

        # 左侧：地图数据操作（数据源相关按钮集中）
        data_ops = ttk.LabelFrame(left, text="地图数据 (pubg.im)", padding=(8, 6))
        data_ops.pack(fill=tk.X, pady=(8, 0))
        row1 = ttk.Frame(data_ops)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="更新全部", style="Accent.TButton", command=self._update_all).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(row1, text="更新当前", command=self._update_current).pack(side=tk.LEFT, padx=(0, 6))
        self.btn_cancel = ttk.Button(row1, text="取消下载", command=self._cancel_download, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT)

        # 右侧预览
        right = ttk.Frame(body, padding=8)
        body.add(right, weight=3)
        self.canvas = MapCanvas(right, data_dir=DATA_DIR)

        view_ops = ttk.LabelFrame(right, text="预览操作", padding=(8, 6))
        view_ops.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(view_ops, text="放大", command=lambda: self.canvas.zoom_by(1.2)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(view_ops, text="缩小", command=lambda: self.canvas.zoom_by(1 / 1.2)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(view_ops, text="适配窗口", command=self.canvas.reset_view).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(view_ops, text="导出 PNG", command=self._export_map).pack(side=tk.LEFT, padx=(12, 4))
        ttk.Button(view_ops, text="游戏覆盖层", command=self._open_overlay).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(
            view_ops,
            text="滚轮缩放 · 左键拖拽 · 默认 右 Ctrl+M 切换覆盖层",
            foreground=COLOR_MUTED,
        ).pack(side=tk.LEFT)

        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 底部状态
        status_frame = ttk.Frame(self, padding=(12, 4, 12, 10))
        status_frame.pack(fill=tk.X)
        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.var_status, foreground=COLOR_MUTED).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT)
        # 状态栏右侧低调版权标识
        pack_copyright_ttk(status_frame, dark=True)

    def _set_status(self, text: str) -> None:
        self.var_status.set(text)

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
            self.tree.insert(
                "",
                tk.END,
                iid=entry.id,
                values=(entry.display_name, status_8x8, updated),
            )

    def _on_select_map(self, _event: tk.Event | None = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        map_id = sel[0]
        self._selected_id = map_id
        path = STORE.image_path(map_id)
        self.canvas.set_image(path if path.is_file() else None, map_id=map_id)
        entry = get_map(map_id)
        if entry and path.is_file():
            self._set_status(f"已加载: {entry.display_name}")
        elif entry:
            self._set_status(f"{entry.display_name} 尚未下载")

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
        self._set_status("正在取消…")

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
        if not messagebox.askyesno(
            "更新全部地图",
            "将从 pubg.im 下载全部地图（启用 8x8 的地图使用带点位的详细版）。\n"
            "文件较大，请确保网络畅通。是否继续？",
        ):
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
            rec = download_single_map(
                entry, STORE, with_8x8=True, on_progress=self._on_download_progress
            )
            manifest = STORE.load_manifest()
            maps = {m.id: m for m in (manifest.maps or [])}
            maps[rec.id] = rec
            from map_fetcher import Manifest

            STORE.save_manifest(
                Manifest(
                    with_8x8=True,
                    updated_at=rec.updated_at,
                    maps=list(maps.values()),
                )
            )

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
            messagebox.showwarning("提示", "当前地图尚未下载，无法导出。")
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
        messagebox.showinfo("导出成功", f"已保存至:\n{dest}")

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
        if self._overlay.is_visible():
            self._set_status(f"覆盖层已显示: {entry.display_name}")
        else:
            self._set_status(f"覆盖层已打开: {entry.display_name}")

    def _on_overlay_visibility(self, visible: bool) -> None:
        if visible:
            title = self._overlay.var_title.get()
            self._set_status(f"覆盖层已显示: {title}")
        else:
            self._set_status("覆盖层已隐藏（快捷键可再次唤起）")

    def _on_overlay_closed(self) -> None:
        self._set_status("覆盖层已关闭（可用快捷键再次唤起）")

    def _on_app_close(self) -> None:
        self._overlay.shutdown_hotkey()
        self.destroy()


def _write_startup_log(exc: BaseException) -> None:
    """打包版启动失败时写入日志，便于排查。"""
    try:
        log_path = APP_DIR / "startup_error.log"
        import traceback

        log_path.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass


def _startup_check() -> None:
    """打包冒烟：验证 tkinter、ctypes、主窗口可初始化（不进入 mainloop）。"""
    import ctypes  # noqa: F401 — 覆盖层依赖，缺 ffi.dll 时此处即失败

    app = PubgMapApp()
    app.update_idletasks()
    app.destroy()


def main() -> None:
    try:
        app = PubgMapApp()
        app.mainloop()
    except Exception as exc:
        if getattr(sys, "frozen", False):
            _write_startup_log(exc)
        try:
            root = tk.Tk()
            root.withdraw()
            hint = f"{exc}\n\n"
            if getattr(sys, "frozen", False):
                hint += f"详情已写入:\n{APP_DIR / 'startup_error.log'}"
            else:
                hint += "请在 pubg_map_tool 目录执行: python main.py"
            messagebox.showerror("启动失败", hint)
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    if "--startup-check" in sys.argv:
        _startup_check()
    else:
        main()
