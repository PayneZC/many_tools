# -*- coding: utf-8 -*-
"""
本地协议配置管理器 — Windows 自定义 URL 协议注册表管理（tkinter + winreg）
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import winreg

CLASSES_PATH = r"Software\Classes"
URL_PROTOCOL_VALUE = "URL Protocol"
DEFAULT_LAUNCH_ARGS = '"%1"'


def is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _open_classes_root():
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSES_PATH)


def list_url_protocols() -> list[str]:
    r"""枚举 HKCU\Software\Classes 下带 URL Protocol 标记的协议键名。"""
    names: list[str] = []
    try:
        with _open_classes_root() as classes_key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(classes_key, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(classes_key, name) as sub:
                        try:
                            winreg.QueryValueEx(sub, URL_PROTOCOL_VALUE)
                            names.append(name)
                        except OSError:
                            pass
                except OSError:
                    continue
    except OSError as e:
        raise PermissionError(str(e)) from e
    names.sort(key=str.lower)
    return names


def read_protocol_detail(scheme: str) -> tuple[str, str, str]:
    """
    返回 (显示名称, 客户端路径, 启动参数)。
    """
    display = ""
    exe_path = ""
    args = DEFAULT_LAUNCH_ARGS
    base = rf"{CLASSES_PATH}\{scheme}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as key:
            try:
                display, _ = winreg.QueryValueEx(key, "")
            except OSError:
                pass
        cmd_key = rf"{base}\shell\open\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmd_key) as cmd:
            try:
                raw, _ = winreg.QueryValueEx(cmd, "")
            except OSError:
                raw = ""
            exe_path, rest = parse_command_line(raw)
            if rest:
                args = rest
            elif not raw:
                args = DEFAULT_LAUNCH_ARGS
    except OSError:
        pass
    return display, exe_path, args


def parse_command_line(cmd: str) -> tuple[str, str]:
    r"""从 shell\open\command 默认值解析可执行路径与剩余参数。"""
    cmd = (cmd or "").strip()
    if not cmd:
        return "", ""
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        if end != -1:
            path = cmd[1:end]
            rest = cmd[end + 1 :].strip()
            return path, rest
    parts = cmd.split(None, 1)
    path = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    return path, rest


def normalize_scheme(text: str) -> str:
    t = (text or "").strip()
    if t.endswith(":"):
        t = t[:-1]
    return t


def validate_scheme(scheme: str) -> bool:
    if not scheme:
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*$", scheme))


def _shell_execute_open(path_or_url: str) -> None:
    """通过 Shell 打开文件或 URL（自定义协议比 cmd start 更可靠）。"""
    ShellExecuteW = ctypes.windll.shell32.ShellExecuteW
    ShellExecuteW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    ShellExecuteW.restype = ctypes.c_size_t
    ret = ShellExecuteW(None, "open", path_or_url, None, None, 1)
    if ret <= 32:
        err_map = {
            2: "找不到指定文件",
            3: "找不到路径",
            5: "拒绝访问",
            8: "内存不足",
            26: "共享冲突",
            31: "没有关联的应用程序",
        }
        hint = err_map.get(ret, f"错误码 {ret}")
        raise OSError(f"无法打开链接：{hint}。若已保存协议，请检查客户端路径与启动参数是否正确。")


def save_protocol(scheme: str, display: str, exe_path: str, launch_args: str) -> None:
    scheme = normalize_scheme(scheme)
    if not validate_scheme(scheme):
        raise ValueError("协议标识无效：需以字母开头，仅含字母、数字、+、.、-")
    raw_path = (exe_path or "").strip()
    exe_path = os.path.normpath(os.path.abspath(raw_path))
    if not exe_path or not os.path.isfile(exe_path):
        raise ValueError("客户端路径无效或文件不存在")

    args = (launch_args or "").strip() or DEFAULT_LAUNCH_ARGS
    quoted = f'"{exe_path}" {args}'.strip()

    base = rf"{CLASSES_PATH}\{scheme}"
    # 创建/打开协议根键
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base)
    try:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, display or scheme)
        winreg.SetValueEx(key, URL_PROTOCOL_VALUE, 0, winreg.REG_SZ, "")
    finally:
        winreg.CloseKey(key)

    cmd_path = rf"{base}\shell\open\command"
    cmd_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cmd_path)
    try:
        winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, quoted)
    finally:
        winreg.CloseKey(cmd_key)


def _delete_key_hkcu(relative_path: str) -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, relative_path)
    except OSError as e:
        if getattr(e, "winerror", None) != 2:
            raise


def delete_protocol(scheme: str) -> None:
    scheme = normalize_scheme(scheme)
    if not scheme:
        raise ValueError("未选择协议")
    base = rf"{CLASSES_PATH}\{scheme}"
    for tail in (r"shell\open\command", r"shell\open", r"shell"):
        _delete_key_hkcu(rf"{base}\{tail}")
    _delete_key_hkcu(base)


def test_invoke_scheme(scheme: str) -> None:
    scheme = normalize_scheme(scheme)
    if not scheme:
        raise ValueError("请填写协议标识")
    url = f"{scheme}://test"
    _shell_execute_open(url)


class ProtocolManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("本地协议配置管理器")
        self.minsize(720, 480)
        self.geometry("900x560")

        self._admin = is_user_admin()
        self._build_ui()
        self.after(100, self._initial_load)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=7)
        self.rowconfigure(1, weight=1)

        # 权限警告条
        warn_frame = tk.Frame(self, bg="#fff3cd", pady=6)
        warn_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        if not self._admin:
            tk.Label(
                warn_frame,
                text="当前权限不足，部分功能可能无法保存，请右键以管理员身份运行",
                bg="#fff3cd",
                fg="#856404",
                font=("Microsoft YaHei UI", 9),
            ).pack(side=tk.LEFT, padx=12)
        else:
            warn_frame.grid_remove()

        # 左侧列表区（约 30%）
        left = ttk.Frame(self, padding=8)
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="协议列表").grid(row=0, column=0, sticky="w")
        btn_row = ttk.Frame(left)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(btn_row, text="刷新", command=self.refresh_list).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="新建", command=self.on_new).pack(side=tk.LEFT)

        self.listbox = tk.Listbox(left, exportselection=False, font=("Consolas", 10))
        self.listbox.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self.on_list_select)

        # 右侧详情区（约 70%）
        right = ttk.Frame(self, padding=8)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(right, text="协议标识").grid(row=r, column=0, sticky="nw", pady=4)
        self.var_scheme = tk.StringVar()
        self.entry_scheme = ttk.Entry(right, textvariable=self.var_scheme, width=48)
        self.entry_scheme.grid(row=r, column=1, sticky="ew", pady=4, padx=(8, 0))
        r += 1
        ttk.Label(right, text="显示名称").grid(row=r, column=0, sticky="nw", pady=4)
        self.var_display = tk.StringVar()
        ttk.Entry(right, textvariable=self.var_display, width=48).grid(
            row=r, column=1, sticky="ew", pady=4, padx=(8, 0)
        )
        r += 1
        ttk.Label(right, text="客户端路径").grid(row=r, column=0, sticky="nw", pady=4)
        path_frame = ttk.Frame(right)
        path_frame.grid(row=r, column=1, sticky="ew", pady=4, padx=(8, 0))
        path_frame.columnconfigure(0, weight=1)
        self.var_path = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.var_path).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(path_frame, text="浏览…", command=self.browse_exe).grid(row=0, column=1)
        r += 1
        ttk.Label(right, text="启动参数").grid(row=r, column=0, sticky="nw", pady=4)
        self.var_args = tk.StringVar(value=DEFAULT_LAUNCH_ARGS)
        ttk.Entry(right, textvariable=self.var_args, width=48).grid(
            row=r, column=1, sticky="ew", pady=4, padx=(8, 0)
        )
        ttk.Label(
            right,
            text="（默认将 URL 作为第一个参数传递；路径保存时会自动加双引号）",
            font=("Microsoft YaHei UI", 8),
            foreground="gray",
        ).grid(row=r + 1, column=1, sticky="w", padx=(8, 0))

        # 底部操作栏
        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(bottom, text="保存配置", command=self.on_save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bottom, text="删除协议", command=self.on_delete).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bottom, text="测试唤起", command=self.on_test).pack(side=tk.LEFT)

        self.status = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status, relief=tk.SUNKEN, anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="ew"
        )

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def _initial_load(self) -> None:
        self.refresh_list(silent=True)

    def refresh_list(self, silent: bool = False) -> None:
        try:
            names = list_url_protocols()
        except PermissionError:
            self.set_status("建议以管理员身份运行：无法完整读取注册表")
            if not silent:
                messagebox.showwarning("权限", "无法读取协议列表，建议以管理员身份运行。")
            return
        self.listbox.delete(0, tk.END)
        for n in names:
            self.listbox.insert(tk.END, n)
        self.set_status(f"已加载 {len(names)} 个协议（当前用户 Classes）")
        if not silent and not names:
            self.set_status("当前用户下未找到自定义 URL 协议，可点击「新建」添加")

    def on_new(self) -> None:
        self.listbox.selection_clear(0, tk.END)
        self.var_scheme.set("")
        self.var_display.set("")
        self.var_path.set("")
        self.var_args.set(DEFAULT_LAUNCH_ARGS)
        self.set_status("新建：请填写协议标识与客户端路径")
        self.entry_scheme.focus_set()

    def on_list_select(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        scheme = self.listbox.get(sel[0])
        display, path, args = read_protocol_detail(scheme)
        self.var_scheme.set(scheme)
        self.var_display.set(display)
        self.var_path.set(path)
        self.var_args.set(args if args else DEFAULT_LAUNCH_ARGS)
        self.set_status(f"已选择：{scheme}")

    def browse_exe(self) -> None:
        p = filedialog.askopenfilename(
            title="选择客户端可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if p:
            self.var_path.set(p)

    def on_save(self) -> None:
        scheme = normalize_scheme(self.var_scheme.get())
        try:
            save_protocol(
                scheme,
                self.var_display.get().strip(),
                self.var_path.get(),
                self.var_args.get(),
            )
        except ValueError as e:
            messagebox.showerror("校验失败", str(e))
            return
        except OSError as e:
            messagebox.showerror("注册表错误", f"写入失败，可能权限不足：\n{e}")
            return
        messagebox.showinfo("成功", "注册成功")
        self.refresh_list(silent=True)
        # 选中刚保存的项
        names = self.listbox.get(0, tk.END)
        if scheme in names:
            idx = names.index(scheme)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)

    def on_delete(self) -> None:
        scheme = normalize_scheme(self.var_scheme.get())
        if not scheme:
            messagebox.showinfo("提示", "请先选择要删除的协议或填写协议标识")
            return
        if not messagebox.askyesno("确认删除", f"确定删除协议「{scheme}」？此操作不可撤销。"):
            return
        try:
            delete_protocol(scheme)
        except OSError as e:
            messagebox.showerror("注册表错误", f"删除失败：\n{e}")
            return
        self.refresh_list(silent=True)
        self.on_new()
        self.set_status(f"已删除：{scheme}")

    def on_test(self) -> None:
        try:
            test_invoke_scheme(self.var_scheme.get())
        except ValueError as e:
            messagebox.showwarning("提示", str(e))
            return
        except OSError as e:
            messagebox.showerror("唤起失败", str(e))
            return
        self.set_status("已尝试打开测试链接（请查看是否启动客户端）")


def main() -> None:
    if sys.platform != "win32":
        print("本程序仅支持 Windows。")
        sys.exit(1)
    app = ProtocolManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
