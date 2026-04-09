"""
Windows 压枪宏（Logitech Lua 脚本的 Python 实现）。

与 Lua 脚本对应的功能：
1) 按住鼠标右键（button 2）时启用压枪开关。
2) 在开关生效时，按住鼠标左键持续向下移动鼠标。
"""

from __future__ import annotations

import ctypes
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

from pynput import mouse


# WinAPI 常量
VK_LBUTTON = 0x01
MOUSEEVENTF_MOVE = 0x0001


user32 = ctypes.windll.user32


def is_pressed(vk_code: int) -> bool:
    return (user32.GetAsyncKeyState(vk_code) & 0x8000) != 0


def move_mouse_relative(dx: int, dy: int) -> None:
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


@dataclass
class RuntimeState:
    # 预留总开关，便于后续扩展（当前默认始终为 True）。
    recoil_enabled: bool = True
    # 仅当右键按住时为 True，对应 Lua 中的 switch。
    switch_enabled: bool = False
    # 防止重复启动多个压枪线程。
    running_loop: bool = False
    # 线程锁：用于保护状态读写，避免并发竞争。
    lock: threading.Lock = field(default_factory=threading.Lock)


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
        # 无论循环如何退出，都要释放运行标记。
        with state.lock:
            state.running_loop = False


def main() -> None:
    state = RuntimeState()
    root = tk.Tk()
    root.title("压枪脚本")
    root.geometry("360x150")
    root.resizable(False, False)

    tip1 = tk.Label(root, text="脚本运行中", font=("Microsoft YaHei UI", 12, "bold"))
    tip1.pack(pady=(18, 8))
    tip2 = tk.Label(root, text="按住右键激活，按住左键执行压枪")
    tip2.pack()
    tip3 = tk.Label(root, text="关闭此窗口将退出程序", fg="gray")
    tip3.pack(pady=(8, 0))

    def on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        # 右键按下/抬起分别设置开关状态。
        if button == mouse.Button.right:
            with state.lock:
                state.switch_enabled = pressed
            return

        # 左键按下时，若条件满足则启动压枪线程。
        if button == mouse.Button.left and pressed:
            with state.lock:
                can_run = state.recoil_enabled and state.switch_enabled and not state.running_loop
            if can_run:
                t = threading.Thread(target=run_recoil_loop, args=(state,), daemon=True)
                t.start()

    listener = mouse.Listener(on_click=on_click)
    listener.start()

    def on_close() -> None:
        try:
            listener.stop()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
