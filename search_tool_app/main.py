#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
目录查询工具（Tkinter）

支持在指定根目录中查询：
1) 目录名包含指定字符串
2) 文件名包含指定字符串
3) 文件内容包含指定字符串
"""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


@dataclass
class SearchConfig:
    root_dir: str
    keyword: str
    search_dirs: bool
    search_files: bool
    search_content: bool
    case_sensitive: bool
    max_results: int
    max_file_size_mb: int
    workers: int
    exclude_dirs: set[str]


class DirectorySearchApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("目录字符串查询工具")
        self.geometry("980x680")
        self.minsize(900, 580)

        self._search_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._result_count = 0
        self._scanned_files = 0
        self._scanned_dirs = 0
        self._start_ts = 0.0

        self._build_ui()
        self.after(120, self._drain_ui_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(8, weight=1)

        ttk.Label(root, text="扫描根目录").grid(row=0, column=0, sticky="w", pady=4)
        self.var_root = tk.StringVar(value=str(Path.cwd()))
        ttk.Entry(root, textvariable=self.var_root).grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 6))
        ttk.Button(root, text="选择目录", command=self._pick_root).grid(row=0, column=2, sticky="e", pady=4)

        ttk.Label(root, text="查询字符串").grid(row=1, column=0, sticky="w", pady=4)
        self.var_keyword = tk.StringVar()
        ttk.Entry(root, textvariable=self.var_keyword).grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 6))

        scope = ttk.Frame(root)
        scope.grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        self.var_search_dirs = tk.BooleanVar(value=True)
        self.var_search_files = tk.BooleanVar(value=True)
        self.var_search_content = tk.BooleanVar(value=True)
        ttk.Checkbutton(scope, text="目录名", variable=self.var_search_dirs).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(scope, text="文件名", variable=self.var_search_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(scope, text="文件内容", variable=self.var_search_content).pack(side=tk.LEFT)

        perf = ttk.Frame(root)
        perf.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(perf, text="最大结果数").pack(side=tk.LEFT)
        self.var_max_results = tk.StringVar(value="1000")
        ttk.Entry(perf, width=8, textvariable=self.var_max_results).pack(side=tk.LEFT, padx=(6, 16))

        ttk.Label(perf, text="最大文件大小(MB)").pack(side=tk.LEFT)
        self.var_max_file_mb = tk.StringVar(value="10")
        ttk.Entry(perf, width=8, textvariable=self.var_max_file_mb).pack(side=tk.LEFT, padx=(6, 16))

        ttk.Label(perf, text="内容扫描线程数").pack(side=tk.LEFT)
        self.var_workers = tk.StringVar(value=str(min(8, max(2, (os.cpu_count() or 4)))))
        ttk.Entry(perf, width=8, textvariable=self.var_workers).pack(side=tk.LEFT, padx=(6, 0))

        opt = ttk.Frame(root)
        opt.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        self.var_case_sensitive = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="区分大小写", variable=self.var_case_sensitive).pack(side=tk.LEFT)

        ttk.Label(root, text="忽略目录(逗号分隔)").grid(row=5, column=0, sticky="w", pady=4)
        self.var_exclude_dirs = tk.StringVar(value=",".join(sorted(DEFAULT_EXCLUDE_DIRS)))
        ttk.Entry(root, textvariable=self.var_exclude_dirs).grid(
            row=5, column=1, columnspan=2, sticky="ew", pady=4, padx=(8, 0)
        )

        actions = ttk.Frame(root)
        actions.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 6))
        self.btn_start = ttk.Button(actions, text="开始查询", command=self._start_search)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(actions, text="停止", command=self._stop_search, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="清空结果", command=self._clear_results).pack(side=tk.LEFT, padx=(8, 0))

        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.var_status).grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.result = tk.Text(root, wrap=tk.NONE, font=("Consolas", 10))
        self.result.grid(row=8, column=0, columnspan=3, sticky="nsew")
        ysb = ttk.Scrollbar(root, orient=tk.VERTICAL, command=self.result.yview)
        xsb = ttk.Scrollbar(root, orient=tk.HORIZONTAL, command=self.result.xview)
        self.result.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        ysb.grid(row=8, column=3, sticky="ns")
        xsb.grid(row=9, column=0, columnspan=3, sticky="ew")

    def _pick_root(self) -> None:
        d = filedialog.askdirectory(title="选择扫描根目录", initialdir=self.var_root.get() or str(Path.cwd()))
        if d:
            self.var_root.set(d)

    def _clear_results(self) -> None:
        self.result.delete("1.0", tk.END)
        self.var_status.set("已清空结果")

    def _set_running(self, running: bool) -> None:
        self.btn_start.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL if running else tk.DISABLED)

    def _parse_config(self) -> SearchConfig | None:
        root_dir = self.var_root.get().strip()
        keyword = self.var_keyword.get()

        if not root_dir or not os.path.isdir(root_dir):
            messagebox.showerror("参数错误", "扫描根目录不存在")
            return None
        if not keyword:
            messagebox.showerror("参数错误", "查询字符串不能为空")
            return None

        try:
            max_results = max(1, int(self.var_max_results.get().strip()))
            max_file_size_mb = max(1, int(self.var_max_file_mb.get().strip()))
            workers = max(1, min(32, int(self.var_workers.get().strip())))
        except ValueError:
            messagebox.showerror("参数错误", "性能参数必须为整数")
            return None

        if not (self.var_search_dirs.get() or self.var_search_files.get() or self.var_search_content.get()):
            messagebox.showerror("参数错误", "至少选择一种查询范围")
            return None

        exclude = {
            item.strip()
            for item in self.var_exclude_dirs.get().split(",")
            if item.strip()
        }

        return SearchConfig(
            root_dir=root_dir,
            keyword=keyword,
            search_dirs=self.var_search_dirs.get(),
            search_files=self.var_search_files.get(),
            search_content=self.var_search_content.get(),
            case_sensitive=self.var_case_sensitive.get(),
            max_results=max_results,
            max_file_size_mb=max_file_size_mb,
            workers=workers,
            exclude_dirs=exclude,
        )

    def _start_search(self) -> None:
        if self._search_thread and self._search_thread.is_alive():
            return

        cfg = self._parse_config()
        if not cfg:
            return

        self._stop_event.clear()
        self._set_running(True)
        self._result_count = 0
        self._scanned_files = 0
        self._scanned_dirs = 0
        self._start_ts = time.time()
        self.result.insert(tk.END, f"开始扫描: {cfg.root_dir}\n")
        self.result.see(tk.END)
        self.var_status.set("查询中...")

        self._search_thread = threading.Thread(target=self._search_worker, args=(cfg,), daemon=True)
        self._search_thread.start()

    def _stop_search(self) -> None:
        self._stop_event.set()
        self.var_status.set("正在停止...")

    def _push_ui(self, action: str, payload: str) -> None:
        self._ui_queue.put((action, payload))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                action, payload = self._ui_queue.get_nowait()
                if action == "append":
                    self.result.insert(tk.END, payload + "\n")
                    self.result.see(tk.END)
                elif action == "status":
                    self.var_status.set(payload)
                elif action == "finish":
                    self._set_running(False)
                    self.var_status.set(payload)
        except queue.Empty:
            pass
        finally:
            self.after(120, self._drain_ui_queue)

    def _try_add_result(self, text: str, cfg: SearchConfig) -> bool:
        if self._result_count >= cfg.max_results:
            return False
        self._result_count += 1
        self._push_ui("append", text)
        return True

    def _search_worker(self, cfg: SearchConfig) -> None:
        keyword = cfg.keyword if cfg.case_sensitive else cfg.keyword.lower()
        max_bytes = cfg.max_file_size_mb * 1024 * 1024

        stop_all = threading.Event()
        content_tasks: queue.Queue[str | None] = queue.Queue(maxsize=4096)

        def normalize_text(s: str) -> str:
            return s if cfg.case_sensitive else s.lower()

        def content_match(file_path: str) -> bool:
            try:
                if os.path.getsize(file_path) > max_bytes:
                    return False
                with open(file_path, "rb") as f:
                    data = f.read()
                if b"\x00" in data:
                    return False
                text = data.decode("utf-8", errors="ignore")
                return keyword in normalize_text(text)
            except OSError:
                return False

        def content_worker() -> None:
            while not self._stop_event.is_set() and not stop_all.is_set():
                file_path = content_tasks.get()
                if file_path is None:
                    content_tasks.task_done()
                    break
                matched = content_match(file_path)
                if matched:
                    if not self._try_add_result(f"[内容] {file_path}", cfg):
                        stop_all.set()
                content_tasks.task_done()

        workers: list[threading.Thread] = []
        if cfg.search_content:
            for _ in range(cfg.workers):
                t = threading.Thread(target=content_worker, daemon=True)
                t.start()
                workers.append(t)

        stack = [cfg.root_dir]
        update_tick = 0

        try:
            while stack and not self._stop_event.is_set() and not stop_all.is_set():
                current = stack.pop()
                self._scanned_dirs += 1
                try:
                    with os.scandir(current) as entries:
                        for entry in entries:
                            if self._stop_event.is_set() or stop_all.is_set():
                                break

                            name_cmp = normalize_text(entry.name)
                            full_path = entry.path

                            if entry.is_dir(follow_symlinks=False):
                                if entry.name in cfg.exclude_dirs:
                                    continue
                                if cfg.search_dirs and keyword in name_cmp:
                                    if not self._try_add_result(f"[目录] {full_path}", cfg):
                                        stop_all.set()
                                        break
                                stack.append(full_path)
                            elif entry.is_file(follow_symlinks=False):
                                self._scanned_files += 1
                                if cfg.search_files and keyword in name_cmp:
                                    if not self._try_add_result(f"[文件] {full_path}", cfg):
                                        stop_all.set()
                                        break
                                if cfg.search_content:
                                    while True:
                                        if self._stop_event.is_set() or stop_all.is_set():
                                            break
                                        try:
                                            content_tasks.put(full_path, timeout=0.2)
                                            break
                                        except queue.Full:
                                            continue
                            update_tick += 1
                            if update_tick % 300 == 0:
                                elapsed = max(time.time() - self._start_ts, 0.001)
                                speed = int((self._scanned_files + self._scanned_dirs) / elapsed)
                                self._push_ui(
                                    "status",
                                    (
                                        f"查询中... 已扫目录 {self._scanned_dirs}，文件 {self._scanned_files}，"
                                        f"命中 {self._result_count}，速度 {speed}/s"
                                    ),
                                )
                except (PermissionError, OSError):
                    continue
        finally:
            if cfg.search_content:
                for _ in workers:
                    content_tasks.put(None)
                content_tasks.join()
                for t in workers:
                    t.join(timeout=0.3)

            elapsed = time.time() - self._start_ts
            status = (
                f"完成：命中 {self._result_count} 条，扫描目录 {self._scanned_dirs}，"
                f"文件 {self._scanned_files}，耗时 {elapsed:.2f}s"
            )
            if self._stop_event.is_set():
                status = (
                    f"已停止：命中 {self._result_count} 条，扫描目录 {self._scanned_dirs}，"
                    f"文件 {self._scanned_files}，耗时 {elapsed:.2f}s"
                )
            elif self._result_count >= cfg.max_results:
                status = (
                    f"达到上限 {cfg.max_results} 条后停止；扫描目录 {self._scanned_dirs}，"
                    f"文件 {self._scanned_files}，耗时 {elapsed:.2f}s"
                )

            self._push_ui("append", "-" * 80)
            self._push_ui("append", status)
            self._push_ui("finish", status)


def main() -> None:
    app = DirectorySearchApp()
    app.mainloop()


if __name__ == "__main__":
    main()
