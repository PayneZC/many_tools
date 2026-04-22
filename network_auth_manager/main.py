#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络认证自动保活工具（Tkinter）

说明：
1) 登录状态通过认证页内容特征判断
2) 掉线后使用爬虫方式请求认证页并提交登录参数
3) 仅保留必要配置：账号、密码、检测间隔(分钟)、超时、执行模式
"""

from __future__ import annotations

import http.cookiejar
import json
import queue
import threading
import time
import tkinter as tk
import webbrowser
import ctypes
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from PIL import Image
import pystray


LOGIN_URL = "http://114.114.114.114:90/"
LOGIN_INDEX_URL = (
    "http://114.114.114.114:90/p/cdbdd4a09a64909694281aec503746fd/"
    "index.html?uri=MTE0LjExNC4xMTQuMTE0Ojkw&authparam=eyJhdXRodHlwZSI6IjUifQ=="
)
LOGIN_SUBMIT_URL = "http://114.114.114.114:90/login"
LOGIN_STATUS_URL = "http://114.114.114.114:90/login?has_ori_uri"
DEFAULT_URI_PARAM = "MTE0LjExNC4xMTQuMTE0Ojkw"
DEFAULT_INTERVAL_MINUTES = 1
DEFAULT_TIMEOUT_SECONDS = 10
APP_ID = "many_tools.network_auth_manager"
MUTEX_NAME = "Global\\ManyTools_NetworkAuthManager_SingleInstance"
ERROR_ALREADY_EXISTS = 183


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_base_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _runtime_base_dir()


def _resolve_config_file() -> Path:
    runtime_config = _runtime_base_dir() / "config.json"
    # 优先使用 exe 同目录，若不可写再回退到用户目录。
    try:
        runtime_config.parent.mkdir(parents=True, exist_ok=True)
        if not runtime_config.exists():
            runtime_config.write_text("{}", encoding="utf-8")
            runtime_config.unlink(missing_ok=True)
        return runtime_config
    except Exception:  # noqa: BLE001
        pass

    user_dir = Path.home() / ".many_tools" / "network_auth_manager"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "config.json"


def _resolve_icon_png() -> Path:
    # 优先运行目录，再尝试 PyInstaller 资源目录
    p = _runtime_base_dir() / "app_icon.png"
    if p.exists():
        return p
    return _resource_base_dir() / "app_icon.png"


def _resolve_icon_ico() -> Path:
    p = _runtime_base_dir() / "app_icon.ico"
    if p.exists():
        return p
    return _resource_base_dir() / "app_icon.ico"


CONFIG_FILE = _resolve_config_file()
APP_ICON_PNG = _resolve_icon_png()
APP_ICON_ICO = _resolve_icon_ico()


def _set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001
        pass


def _acquire_single_instance_mutex() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return None
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(handle)
            return 0
        return int(handle)
    except Exception:  # noqa: BLE001
        return None


def _release_single_instance_mutex(handle: int | None) -> None:
    if sys.platform != "win32" or not handle:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        pass


@dataclass
class AuthConfig:
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    username: str = ""
    password: str = ""
    execute_mode: str = "visible"  # visible / silent
    auto_start_monitor: bool = True  # 程序启动后是否自动启动监听


class AuthClient:
    def __init__(self) -> None:
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        self._jar = http.cookiejar.CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._jar))

    def check_auth_online(self, timeout_seconds: int) -> tuple[bool, str]:
        """
        通过页面内容判断登录状态：
        - 不是登录页
        - 且页面中包含“成功登录/成功登陆”或“退出”按钮
        """
        try:
            req = Request(
                LOGIN_STATUS_URL,
                headers={**self._headers, "Referer": LOGIN_URL},
                method="GET",
            )
            with self._open(req, timeout_seconds=timeout_seconds) as resp:
                code = getattr(resp, "status", 200)
                final_url = getattr(resp, "geturl", lambda: LOGIN_STATUS_URL)()
                html = resp.read().decode("utf-8", errors="ignore")

            lower = html.lower()
            is_login_page = (
                ('id="login_button"' in lower)
                or ("placeholder=\"账号\"" in html)
                or ("placeholder=\"密码\"" in html)
                or ("name=\"pwd\"" in lower)
            )
            has_success_text = ("成功登录" in html) or ("成功登陆" in html) or ("已经成功登录" in html)
            has_logout = ("btn_quit" in lower) or (">退出<" in html) or ("value=\"退出\"" in html)
            is_online = (not is_login_page) and (has_success_text or has_logout)

            if is_online:
                return True, f"认证状态在线: HTTP {code}, {final_url}"
            return False, f"认证状态离线: HTTP {code}, {final_url}"
        except Exception as exc:  # noqa: BLE001
            return False, f"认证状态检测失败: {exc}"

    @staticmethod
    def _md6(text: str) -> str:
        """
        按认证页 client.js 中 core.str.md6 逻辑实现密码转换。
        """

        def mc(a: int) -> str:
            table = "0123456789ABCDEF"
            if a == ord(" "):
                return "+"
            if (
                (a < ord("0") and a not in (ord("-"), ord(".")))
                or (ord("9") < a < ord("A"))
                or (ord("Z") < a < ord("a") and a != ord("_"))
                or (a > ord("z"))
            ):
                return "%" + table[(a >> 4) & 15] + table[a & 15]
            return chr(a)

        def bit_reverse_byte(a: int) -> int:
            return (
                ((a & 1) << 7)
                | ((a & 0x2) << 5)
                | ((a & 0x4) << 3)
                | ((a & 0x8) << 1)
                | ((a & 0x10) >> 1)
                | ((a & 0x20) >> 3)
                | ((a & 0x40) >> 5)
                | ((a & 0x80) >> 7)
            )

        out = []
        for i, ch in enumerate(text):
            c = bit_reverse_byte(ord(ch)) ^ (0x35 ^ (i & 0xFF))
            out.append(mc(c))
        return "".join(out)

    def _open(self, req: Request, timeout_seconds: int):
        try:
            return self._opener.open(req, timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            text = str(exc).lower()
            # 避免因为偶发压缩流不完整直接失败；退回到无压缩再试一次。
            if "end-of-stream marker" in text:
                headers = dict(req.header_items())
                headers.pop("Accept-encoding", None)
                retry = Request(
                    url=req.full_url,
                    data=req.data,
                    method=req.get_method(),
                    headers=headers,
                )
                return self._opener.open(retry, timeout=timeout_seconds)
            raise

    @staticmethod
    def _extract_uri_param(from_url: str) -> str:
        parsed = urlparse(from_url)
        query = parse_qs(parsed.query)
        uri = (query.get("uri") or [""])[0].strip()
        return uri or DEFAULT_URI_PARAM

    def auto_login_with_crawler(
        self,
        username: str,
        password: str,
        timeout_seconds: int,
        visible: bool,
    ) -> tuple[bool, str]:
        if not username:
            return False, "账号为空，无法自动登录"
        if not password:
            return False, "密码为空，无法自动登录"

        try:
            # 可视模式仅用于排查（同时保留爬虫登录主流程）。
            if visible:
                webbrowser.open(LOGIN_URL, new=2)

            # 第一步：进入认证页，拿到 cookie 与 uri 参数。
            index_req = Request(
                LOGIN_INDEX_URL,
                headers={
                    **self._headers,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": LOGIN_URL,
                },
                method="GET",
            )
            with self._open(index_req, timeout_seconds=timeout_seconds) as resp:
                final_url = getattr(resp, "geturl", lambda: LOGIN_INDEX_URL)()
                _ = resp.read()  # 需要消费响应，确保 cookie 生效

            uri_param = self._extract_uri_param(final_url)
            encoded_password = self._md6(password)
            payload = {
                "page_version": "10.0",
                "username": username,
                "password": encoded_password,
                "login_type": "login",
                "page_language": "zh",
                "terminal": "pc",
                "uri": uri_param,
            }
            body = urlencode(payload).encode("utf-8")

            # 第二步：模拟点击登录（本质是 POST /login）。
            submit_req = Request(
                LOGIN_SUBMIT_URL,
                data=body,
                method="POST",
                headers={
                    **self._headers,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "http://114.114.114.114:90",
                    "Referer": final_url,
                },
            )
            with self._open(submit_req, timeout_seconds=timeout_seconds) as resp:
                code = getattr(resp, "status", 200)
                content_type = (resp.headers.get("Content-Type") or "").lower()
                text = resp.read().decode("utf-8", errors="ignore")

            # /login 在不同状态下可能回 JSON，也可能返回 HTML。
            lower = text.lower()
            if code >= 400:
                return False, f"登录接口返回异常状态码: HTTP {code}"
            if "application/json" in content_type:
                # JSON 情况下以关键字段做容错判断。
                try:
                    obj = json.loads(text)
                    compact = json.dumps(obj, ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    compact = text[:240].replace("\n", " ")
                return True, f"登录请求已提交(JSON): HTTP {code}, 响应: {compact[:240]}"

            # HTML 情况下做弱判断，后续仍以“登录后二次探测”作为最终准则。
            if ("成功登录" in text) or ("您已经成功登录" in text):
                return True, f"登录请求已提交(HTML): HTTP {code}，页面显示成功登录"
            if ("用户认证系统" in text) and ("password" in lower or "pwd" in lower):
                return True, f"登录请求已提交(HTML): HTTP {code}，返回认证页面（将以网络复测判定结果）"
            return True, f"登录请求已提交: HTTP {code}，返回内容长度 {len(text)}"
        except Exception as exc:  # noqa: BLE001
            return False, f"爬虫登录异常: {exc}"


class NetworkAuthManagerApp(tk.Tk):
    def __init__(self) -> None:
        _set_app_user_model_id()
        super().__init__()
        self.title("网络认证自动保活工具")
        self.geometry("900x620")
        self.minsize(840, 560)

        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._client = AuthClient()
        self._tray_icon: pystray.Icon | None = None
        self._is_quitting = False
        self._icon_photo: tk.PhotoImage | None = None
        self._is_monitor_running = False

        self._build_ui()
        self._load_config_to_ui()
        self._apply_window_icon()
        self.after(120, self._drain_queue)
        # 窗口初始化完成后，根据配置自动启动监听。
        self.after(300, self._auto_start_monitor_if_enabled)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(4, weight=1)

        auth = ttk.LabelFrame(root, text="认证账号")
        auth.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        auth.columnconfigure(1, weight=1)
        ttk.Label(auth, text="账号").grid(row=0, column=0, sticky="w", pady=4)
        self.var_username = tk.StringVar()
        ttk.Entry(auth, textvariable=self.var_username).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)
        ttk.Label(auth, text="密码").grid(row=1, column=0, sticky="w", pady=4)
        self.var_password = tk.StringVar()
        ttk.Entry(auth, textvariable=self.var_password, show="*").grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)

        perf = ttk.Frame(root)
        perf.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(perf, text="检测间隔(分钟)").pack(side=tk.LEFT)
        self.var_interval = tk.StringVar(value=str(DEFAULT_INTERVAL_MINUTES))
        ttk.Entry(perf, width=10, textvariable=self.var_interval).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(perf, text="超时(秒)").pack(side=tk.LEFT)
        self.var_timeout = tk.StringVar(value=str(DEFAULT_TIMEOUT_SECONDS))
        ttk.Entry(perf, width=10, textvariable=self.var_timeout).pack(side=tk.LEFT, padx=(6, 16))

        ttk.Label(perf, text="执行模式").pack(side=tk.LEFT)
        self.var_mode = tk.StringVar(value="visible")
        ttk.Radiobutton(perf, text="显示执行", value="visible", variable=self.var_mode).pack(side=tk.LEFT, padx=(6, 4))
        ttk.Radiobutton(perf, text="静默执行", value="silent", variable=self.var_mode).pack(side=tk.LEFT)
        self.var_auto_start = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            perf,
            text="启动程序时自动启动监听",
            variable=self.var_auto_start,
        ).pack(side=tk.LEFT, padx=(16, 0))

        actions = ttk.Frame(root)
        actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))
        # 使用单一开关按钮控制监听启动与停止，减少操作复杂度。
        self.btn_toggle_monitor = ttk.Button(actions, text="开启监听", command=self._toggle_monitor)
        self.btn_toggle_monitor.pack(side=tk.LEFT)
        ttk.Button(actions, text="立即检测并尝试登录", command=self._manual_check_and_login).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="保存配置", command=self._save_config_from_ui).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="清空日志", command=self._clear_logs).pack(side=tk.LEFT, padx=(8, 0))

        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.var_status).grid(row=3, column=0, columnspan=2, sticky="w")

        self.log_box = tk.Text(root, wrap=tk.WORD, height=18, font=("Consolas", 10))
        self.log_box.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        sb = ttk.Scrollbar(root, orient=tk.VERTICAL, command=self.log_box.yview)
        sb.grid(row=4, column=2, sticky="ns", pady=(6, 0))
        self.log_box.configure(yscrollcommand=sb.set)

    def _queue_log(self, text: str) -> None:
        self._queue.put(("log", text))

    def _queue_status(self, text: str) -> None:
        self._queue.put(("status", text))

    def _drain_queue(self) -> None:
        try:
            while True:
                action, text = self._queue.get_nowait()
                if action == "log":
                    now = time.strftime("%H:%M:%S")
                    self.log_box.insert(tk.END, f"[{now}] {text}\n")
                    self.log_box.see(tk.END)
                elif action == "status":
                    self.var_status.set(text)
                elif action == "running":
                    running = text == "1"
                    self._is_monitor_running = running
                    self.btn_toggle_monitor.configure(text="关闭监听" if running else "开启监听")
        except queue.Empty:
            pass
        finally:
            self.after(120, self._drain_queue)

    def _clear_logs(self) -> None:
        self.log_box.delete("1.0", tk.END)
        self._queue_status("日志已清空")

    def _apply_window_icon(self) -> None:
        if APP_ICON_PNG.exists():
            try:
                self._icon_photo = tk.PhotoImage(file=str(APP_ICON_PNG))
                self.iconphoto(True, self._icon_photo)
            except Exception:  # noqa: BLE001
                self._icon_photo = None
        if APP_ICON_ICO.exists():
            try:
                self.iconbitmap(str(APP_ICON_ICO))
            except Exception:  # noqa: BLE001
                pass

    def _get_tray_image(self) -> Image.Image:
        if APP_ICON_PNG.exists():
            return Image.open(APP_ICON_PNG).convert("RGBA")
        if APP_ICON_ICO.exists():
            return Image.open(APP_ICON_ICO).convert("RGBA")
        # 兜底纯色图标，避免托盘初始化失败
        return Image.new("RGBA", (64, 64), (27, 96, 196, 255))

    def _create_tray_icon(self) -> bool:
        if self._tray_icon is not None:
            return True
        try:
            image = self._get_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem(
                    "显示界面",
                    self._tray_on_show,
                    default=True,
                ),
                pystray.MenuItem("退出", self._tray_on_exit),
            )
            self._tray_icon = pystray.Icon("network_auth_manager", image, "网络认证自动保活工具", menu)
            self._tray_icon.run_detached()
            return True
        except Exception as exc:  # noqa: BLE001
            self._queue_log(f"托盘初始化失败：{exc}")
            return False

    def _tray_on_show(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _ = icon, item
        self.after(0, self._restore_from_tray)

    def _tray_on_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _ = icon, item
        self.after(0, self._quit_application)

    def _hide_to_tray(self) -> None:
        if not self._create_tray_icon():
            self._quit_application()
            return
        self.withdraw()
        self._queue_status("已最小化到系统托盘")
        self._queue_log("窗口已最小化到系统托盘")

    def _restore_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self._queue_status("已恢复窗口")

    def _stop_tray_icon(self) -> None:
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._tray_icon = None

    def _quit_application(self) -> None:
        if self._is_quitting:
            return
        self._is_quitting = True
        self._stop_event.set()
        self._stop_tray_icon()
        self.destroy()

    def _read_ui_config(self) -> AuthConfig | None:
        try:
            interval = max(1, int(self.var_interval.get().strip()))
            timeout = max(5, int(self.var_timeout.get().strip()))
        except ValueError:
            messagebox.showerror("参数错误", "检测间隔(分钟)和超时必须为整数")
            return None

        cfg = AuthConfig(
            interval_minutes=interval,
            timeout_seconds=timeout,
            username=self.var_username.get().strip(),
            password=self.var_password.get(),
            execute_mode=self.var_mode.get().strip() or "visible",
            # 记录用户对“启动后自动监听”的选择，便于下次启动沿用。
            auto_start_monitor=bool(self.var_auto_start.get()),
        )
        if cfg.execute_mode not in {"visible", "silent"}:
            cfg.execute_mode = "visible"
        return cfg

    def _load_config_to_ui(self) -> None:
        cfg = self._load_config()
        self.var_interval.set(str(cfg.interval_minutes))
        self.var_timeout.set(str(cfg.timeout_seconds))
        self.var_username.set(cfg.username)
        self.var_password.set(cfg.password)
        self.var_mode.set(cfg.execute_mode)
        self.var_auto_start.set(bool(cfg.auto_start_monitor))

    def _load_config(self) -> AuthConfig:
        if not CONFIG_FILE.exists():
            return AuthConfig()
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg = AuthConfig()
            valid_keys = {f.name for f in fields(AuthConfig)}
            for k, v in raw.items():
                if k in valid_keys:
                    setattr(cfg, k, v)
            # 兼容旧版本配置：interval_seconds -> interval_minutes
            if "interval_minutes" not in raw and "interval_seconds" in raw:
                try:
                    old_seconds = int(raw["interval_seconds"])
                    cfg.interval_minutes = max(1, old_seconds // 60)
                    if old_seconds % 60 != 0:
                        cfg.interval_minutes += 1
                except Exception:  # noqa: BLE001
                    cfg.interval_minutes = DEFAULT_INTERVAL_MINUTES
            if cfg.execute_mode not in {"visible", "silent"}:
                cfg.execute_mode = "visible"
            return cfg
        except Exception:  # noqa: BLE001
            return AuthConfig()

    def _auto_start_monitor_if_enabled(self) -> None:
        # 启动后根据配置自动拉起监听，避免每次手动点击。
        if bool(self.var_auto_start.get()):
            self._queue_log("已启用“启动自动监听”，正在自动开启监听")
            self._start_monitor()

    def _toggle_monitor(self) -> None:
        # 单按钮切换监听状态：运行中则停止，未运行则启动。
        if self._is_monitor_running:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _save_config_from_ui(self) -> None:
        cfg = self._read_ui_config()
        if not cfg:
            return
        try:
            CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("保存失败", f"写入配置失败：{exc}")
            return
        self._queue_log("配置已保存")
        self._queue_status("配置保存成功")

    def _start_monitor(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        cfg = self._read_ui_config()
        if not cfg:
            return
        self._save_config_from_ui()
        self._stop_event.clear()
        self._queue.put(("running", "1"))
        self._queue_status("监控中...")
        self._queue_log("开始监控网络认证状态")
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()

    def _stop_monitor(self) -> None:
        self._stop_event.set()
        self._queue.put(("running", "0"))
        self._queue_status("已停止")
        self._queue_log("监控已停止")

    def _manual_check_and_login(self) -> None:
        cfg = self._read_ui_config()
        if not cfg:
            return
        self._save_config_from_ui()
        threading.Thread(target=self._run_single_cycle, args=(cfg,), daemon=True).start()

    def _run_single_cycle(self, cfg: AuthConfig) -> None:
        online, detail = self._client.check_auth_online(timeout_seconds=cfg.timeout_seconds)
        if online:
            self._queue_status("在线")
            self._queue_log(f"认证状态正常，无需重登。{detail}")
            return

        self._queue_status("疑似掉线，尝试自动登录...")
        self._queue_log(f"认证状态离线：{detail}")
        visible = cfg.execute_mode == "visible"

        ok, login_msg = self._client.auto_login_with_crawler(
            username=cfg.username,
            password=cfg.password,
            timeout_seconds=cfg.timeout_seconds,
            visible=visible,
        )
        if not ok:
            self._queue_status("自动登录失败")
            self._queue_log(login_msg)
            return

        self._queue_log(login_msg)
        time.sleep(2.0)
        online_after, detail_after = self._client.check_auth_online(timeout_seconds=cfg.timeout_seconds)
        if online_after:
            self._queue_status("自动登录成功，认证已恢复")
            self._queue_log(f"登录后认证检测成功。{detail_after}")
        else:
            self._queue_status("已提交登录，但认证仍未恢复")
            self._queue_log(f"登录后仍离线：{detail_after}")

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            cfg = self._read_ui_config()
            if not cfg:
                self._queue_status("参数异常，请检查配置")
                self._queue_log("监控停止：参数无效")
                self._queue.put(("running", "0"))
                return
            self._run_single_cycle(cfg)

            waited = 0
            wait_seconds = cfg.interval_minutes * 60
            while waited < wait_seconds and not self._stop_event.is_set():
                time.sleep(1)
                waited += 1

        self._queue.put(("running", "0"))

    def _on_close(self) -> None:
        self._hide_to_tray()


def main() -> None:
    mutex = _acquire_single_instance_mutex()
    if mutex == 0:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("提示", "程序已在运行中（仅允许单实例）。")
        root.destroy()
        return
    try:
        app = NetworkAuthManagerApp()
        app.mainloop()
    finally:
        _release_single_instance_mutex(mutex)


if __name__ == "__main__":
    main()
