# -*- coding: utf-8 -*-
"""覆盖层全局快捷键：解析、内联控件录制与 pynput 监听。"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable

# 修饰键别名 -> pynput GlobalHotKeys 片段
# 存储名 -> pynput 修饰标签（左右 Ctrl 均映射为 <ctrl>）
_MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "shift": "shift",
    "shift_r": "shift",
    "win": "cmd",
    "windows": "cmd",
    "cmd": "cmd",
    "meta": "cmd",
}

# 界面展示用标签
_MODIFIER_LABELS: dict[str, str] = {
    "ctrl": "Ctrl",
    "ctrl_l": "左 Ctrl",
    "ctrl_r": "右 Ctrl",
    "alt": "Alt",
    "alt_l": "左 Alt",
    "alt_r": "右 Alt",
    "alt_gr": "右 Alt",
    "shift": "Shift",
    "shift_r": "右 Shift",
    "win": "Win",
}

_MODIFIER_ORDER = ("ctrl", "ctrl_l", "ctrl_r", "alt", "shift", "win")

# pynput Key 名称 -> 存储用短名（左右键统一为 ctrl/alt/shift）
_KEY_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl_l",
    "ctrl_r": "ctrl_r",
    "alt": "alt",
    "alt_l": "alt_l",
    "alt_r": "alt_r",
    "alt_gr": "alt_r",
    "shift": "shift",
    "shift_r": "shift_r",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
}

# Windows 虚拟键码 -> 修饰键（Listener 有时用 KeyCode 上报修饰键）
_MODIFIER_VK: dict[int, str] = {
    160: "shift",
    161: "shift_r",
    162: "ctrl_l",
    163: "ctrl_r",
    164: "alt_l",
    165: "alt_r",
}


@dataclass(frozen=True)
class HotkeySpec:
    """规范化快捷键，如 ctrl_r+m。"""

    raw: str

    def normalized(self) -> str:
        return self.raw.strip().lower()

    def display(self) -> str:
        """界面展示：右 Ctrl + M"""
        parts = [p.strip() for p in self.normalized().split("+") if p.strip()]
        labels = []
        for p in parts:
            if p in _MODIFIER_LABELS:
                labels.append(_MODIFIER_LABELS[p])
            elif p in _MODIFIER_ALIASES:
                labels.append(p.capitalize() if p != "win" else "Win")
            elif p.startswith("f") and p[1:].isdigit():
                labels.append(p.upper())
            elif len(p) == 1:
                labels.append(p.upper())
            else:
                labels.append(p.capitalize())
        return " + ".join(labels) if labels else "（未设置）"

    def to_pynput(self) -> str | None:
        """转为 pynput GlobalHotKeys 格式，如 <ctrl>+<alt>+m。"""
        parts = [p.strip().lower() for p in self.normalized().split("+") if p.strip()]
        if not parts:
            return None
        mods: list[str] = []
        key_part: str | None = None
        for p in parts:
            if p in _MODIFIER_ALIASES:
                tag = _MODIFIER_ALIASES[p]
                if f"<{tag}>" not in mods:
                    mods.append(f"<{tag}>")
            elif key_part is None:
                key_part = p
            else:
                return None
        if not key_part:
            return None
        if key_part.startswith("f") and key_part[1:].isdigit():
            key_token = f"<{key_part}>"
        elif len(key_part) == 1:
            key_token = key_part
        elif key_part == "space":
            key_token = "<space>"
        else:
            key_token = f"<{key_part}>"
        return "+".join(mods + [key_token]) if mods else key_token


def parse_hotkey(text: str) -> HotkeySpec | None:
    """解析用户输入或录制结果。"""
    t = text.strip().lower().replace("-", "+")
    if not t:
        return None
    parts = [p for p in t.split("+") if p]
    if not parts:
        return None
    return HotkeySpec("+".join(parts))


def _key_to_storage(key) -> str | None:
    """将 pynput 按键转为存储片段；支持左右修饰键与 Alt/Ctrl 组合字母。"""
    from pynput.keyboard import Key, KeyCode

    if isinstance(key, KeyCode):
        vk = getattr(key, "vk", None)
        if vk is not None and vk in _MODIFIER_VK:
            return _MODIFIER_VK[vk]
        if key.char and key.char.isprintable() and ord(key.char) >= 32:
            return key.char.lower()
        if vk is not None:
            # 主键盘 A-Z（按住 Alt 时 char 常为空，vk 仍有效）
            if 65 <= vk <= 90:
                return chr(vk).lower()
            if 97 <= vk <= 122:
                return chr(vk).lower()
            if 48 <= vk <= 57:
                return chr(vk)
            if 96 <= vk <= 105:
                return chr(vk - 48)
        return None
    if isinstance(key, Key):
        n = (key.name or "").lower()
        if n in _KEY_ALIASES:
            return _KEY_ALIASES[n]
        if n in _MODIFIER_ALIASES:
            return n
        if n.startswith("f") and len(n) > 1 and n[1:].isdigit():
            return n
        if n == "space":
            return "space"
    return None


def _format_combo(mods: set[str], main: str | None = None) -> str:
    order = {m: i for i, m in enumerate(_MODIFIER_ORDER)}
    parts = sorted(mods, key=lambda x: order.get(x, 99))
    if main:
        parts.append(main)
    return "+".join(parts)


class GlobalHotkeysHub:
    """
    同一主窗口合并多组全局热键。
    Windows 上多个 GlobalHotKeys 会互相抢占，导致后注册的快捷键失效。
    """

    _instances: dict[int, GlobalHotkeysHub] = {}

    @classmethod
    def for_master(cls, master: tk.Misc) -> GlobalHotkeysHub:
        key = id(master)
        hub = cls._instances.get(key)
        if hub is None:
            hub = cls(master)
            cls._instances[key] = hub
        return hub

    def __init__(self, master: tk.Misc) -> None:
        self._master = master
        self._slots: dict[str, tuple[bool, str, Callable[[], None]]] = {}
        self._handle = None

    def apply_slot(self, slot: str, enabled: bool, hotkey: str, callback: Callable[[], None]) -> bool:
        """注册或更新一个热键槽位，并重建合并后的监听。"""
        self._slots[slot] = (enabled, hotkey, callback)
        return self._restart()

    def remove_slot(self, slot: str) -> None:
        """移除槽位（录入新快捷键前临时停用该组）。"""
        self._slots.pop(slot, None)
        self._restart()

    def _restart(self) -> bool:
        if self._handle is not None:
            try:
                self._handle.stop()
            except Exception:
                pass
            self._handle = None

        mapping: dict[str, Callable[[], None]] = {}
        for _slot, (enabled, hotkey, callback) in self._slots.items():
            if not enabled:
                continue
            spec = parse_hotkey(hotkey)
            if not spec:
                continue
            fmt = spec.to_pynput()
            if not fmt:
                continue
            if fmt in mapping:
                return False

            def _fire(cb: Callable[[], None] = callback) -> None:
                try:
                    self._master.after(0, cb)
                except Exception:
                    pass

            mapping[fmt] = _fire

        if not mapping:
            return True
        try:
            from pynput import keyboard

            self._handle = keyboard.GlobalHotKeys(mapping)
            self._handle.start()
            return True
        except Exception:
            self._handle = None
            return False


class OverlayHotkeyManager:
    """全局热键监听，在 Tk 主线程触发回调。"""

    def __init__(
        self,
        master: tk.Misc,
        on_toggle: Callable[[], None],
        *,
        slot: str | None = None,
    ) -> None:
        self._master = master
        self._on_toggle = on_toggle
        self._slot = slot or f"hotkey_{id(self)}"
        self._hub = GlobalHotkeysHub.for_master(master)

    def apply(self, enabled: bool, hotkey: str) -> bool:
        """应用设置；返回是否成功注册。"""
        return self._hub.apply_slot(self._slot, enabled, hotkey, self._on_toggle)

    def stop(self) -> None:
        self._hub.remove_slot(self._slot)


class InlineHotkeyCapture(tk.Frame):
    """
    内联快捷键录入：点击区域后直接在控件上显示组合键，无需弹窗。
    需同时按下修饰键 + 主键（如 Ctrl+Alt+M）；仅修饰键不会完成录入。
    """

    def __init__(
        self,
        master: tk.Misc,
        var: tk.StringVar,
        *,
        bg: str,
        fg: str,
        accent: str,
        muted: str,
        panel: str,
        on_changed: Callable[[], None] | None = None,
        on_capture_start: Callable[[], None] | None = None,
        on_capture_end: Callable[[], None] | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(master, bg=bg)
        self._var = var
        self._on_changed = on_changed
        self._on_capture_start = on_capture_start
        self._on_capture_end = on_capture_end
        self._colors = {"bg": panel, "fg": fg, "accent": accent, "muted": muted}
        self._recording = False
        self._mods: set[str] = set()
        self._listener = None
        self._esc_bind_id: str | None = None
        # 注释：紧凑模式用于与总开关等同行的快捷键录入。
        padx, pady = (6, 3) if compact else (10, 8)
        font = ("Consolas", 9) if compact else ("Consolas", 11)

        self._label = tk.Label(
            self,
            text=self._display_text(),
            bg=panel,
            fg=fg,
            font=font,
            cursor="hand2",
            padx=padx,
            pady=pady,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=muted,
            highlightcolor=accent,
        )
        if compact:
            self._label.pack(side=tk.LEFT)
        else:
            self._label.pack(fill=tk.BOTH, expand=True)
        self._label.bind("<Button-1>", lambda _e: self._begin_capture())
        self.bind("<Button-1>", lambda _e: self._begin_capture())

    def _display_text(self) -> str:
        spec = parse_hotkey(self._var.get())
        if spec:
            return spec.display()
        return "点击此处录入组合键"

    def refresh(self) -> None:
        if not self._recording:
            self._label.config(text=self._display_text(), bg=self._colors["bg"], fg=self._colors["fg"])

    def _begin_capture(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._mods.clear()
        if self._on_capture_start:
            self._on_capture_start()
        self._label.config(
            text="请按下组合键（Esc 取消）…",
            bg=self._colors["accent"],
            fg="#1e1e2e",
        )
        root = self.winfo_toplevel()
        self._esc_bind_id = root.bind("<Escape>", self._cancel_capture, add="+")

        from pynput import keyboard

        def on_press(key) -> None:
            name = _key_to_storage(key)
            if not name:
                return
            if name in _MODIFIER_ALIASES:
                self._mods.add(name)
                preview = _format_combo(self._mods)
                disp = HotkeySpec(preview).display() if preview else "…"
                self._label.after(0, lambda: self._label.config(text=f"{disp} + …"))
                return
            # 主键按下：与当前已按住修饰键组成组合
            combo = _format_combo(self._mods, name)
            if not combo:
                return
            self._var.set(combo)
            self.after(0, self._finish_capture)

        def on_release(key) -> None:
            n = _key_to_storage(key)
            if n in _MODIFIER_ALIASES and n in self._mods:
                self._mods.discard(n)
                if self._recording and self._mods:
                    preview = HotkeySpec(_format_combo(self._mods)).display() + " + …"
                    self._label.after(0, lambda p=preview: self._label.config(text=p))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def _cancel_capture(self, _event=None) -> None:
        self._finish_capture(cancelled=True)

    def _finish_capture(self, *, cancelled: bool = False) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        root = self.winfo_toplevel()
        if self._esc_bind_id:
            try:
                root.unbind("<Escape>", self._esc_bind_id)
            except tk.TclError:
                pass
            self._esc_bind_id = None
        self.refresh()
        if not cancelled and self._on_changed:
            self._on_changed()
        if self._on_capture_end:
            self._on_capture_end()
