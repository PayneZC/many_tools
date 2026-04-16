"""
鼠标移动测试脚本
模拟FPS游戏中抬枪时的鼠标不规则移动
"""

import ctypes
import time
import random
import tkinter as tk

MOUSEEVENTF_MOVE = 0x0001

user32 = ctypes.windll.user32


def move_mouse_relative(dx: int, dy: int) -> None:
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


def main():
    root = tk.Tk()
    root.title("鼠标移动测试")
    root.geometry("250x120")
    root.resizable(False, False)

    running = [False]
    job = [None]

    label = tk.Label(root, text="状态：已停止", font=("Microsoft YaHei UI", 11))
    label.pack(pady=(15, 10))

    def toggle():
        running[0] = not running[0]
        if running[0]:
            btn.config(text="停止移动")
            label.config(text="状态：移动中...")
            run_loop()
        else:
            btn.config(text="开始移动")
            label.config(text="状态：已停止")
            if job[0]:
                root.after_cancel(job[0])
                job[0] = None

    def run_loop():
        if not running[0]:
            return
        dx = random.randint(-15, 15)
        dy = 25
        move_mouse_relative(dx, -dy)
        job[0] = root.after(50, run_loop)

    btn = tk.Button(root, text="开始移动", command=toggle, width=15, height=2)
    btn.pack(pady=(0, 10))

    tip = tk.Label(root, text="开启后鼠标会自动移动，用于测试锁鼠功能", fg="gray", font=("Microsoft YaHei UI", 8))
    tip.pack()

    def on_close():
        running[0] = False
        if job[0]:
            root.after_cancel(job[0])
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()