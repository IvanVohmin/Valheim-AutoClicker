import ctypes
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from pynput import keyboard


if sys.platform != "win32":
    raise RuntimeError("This script is designed for Windows because it uses the WinAPI SendInput.")


user32 = ctypes.windll.user32

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

MOUSE_BUTTON_EVENTS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    )


class INPUTUNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", ctypes.c_ulong),
        ("union", INPUTUNION),
    )


def mouse_event(flags: int) -> bool:
    extra = ctypes.c_ulong(0)
    inp = INPUT(
        type=INPUT_MOUSE,
        union=INPUTUNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=ctypes.pointer(extra),
            )
        ),
    )

    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    return sent == 1


def send_mouse_click(mouse_button: str, hold_seconds: float) -> bool:
    down_flag, up_flag = MOUSE_BUTTON_EVENTS.get(mouse_button, MOUSE_BUTTON_EVENTS["left"])
    down_ok = mouse_event(down_flag)
    time.sleep(hold_seconds)
    up_ok = mouse_event(up_flag)
    return down_ok and up_ok


@dataclass
class ClickerSettings:
    cps: float = 15.0
    hold_ms: float = 18.0
    mouse_button: str = "left"

    MIN_CPS: float = 1.0
    MAX_CPS: float = 60.0
    MIN_HOLD_MS: float = 1.0
    MAX_HOLD_MS: float = 80.0

    @classmethod
    def from_strings(cls, cps_text: str, hold_text: str, mouse_button: str = "left") -> "ClickerSettings":
        cps = float(cps_text.strip().replace(",", "."))
        hold_ms = float(hold_text.strip().replace(",", "."))

        cps = max(cls.MIN_CPS, min(cls.MAX_CPS, cps))
        hold_ms = max(cls.MIN_HOLD_MS, min(cls.MAX_HOLD_MS, hold_ms))
        mouse_button = mouse_button if mouse_button in MOUSE_BUTTON_EVENTS else "left"

        return cls(cps=cps, hold_ms=hold_ms, mouse_button=mouse_button)


def format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


class ValheimAutoClicker(tk.Tk):
    WINDOW_WIDTH = 680
    WINDOW_HEIGHT = 570

    COLOR_BG = "#0f1117"
    COLOR_CARD = "#151a23"
    COLOR_FIELD = "#0f1117"
    COLOR_BORDER = "#2a3140"
    COLOR_TEXT = "#e5e7eb"
    COLOR_MUTED = "#9ca3af"
    COLOR_WHITE = "#ffffff"
    COLOR_BLUE = "#2563eb"
    COLOR_BLUE_HOVER = "#1d4ed8"
    COLOR_BLUE_PRESSED = "#1e40af"
    COLOR_RED = "#dc2626"
    COLOR_RED_HOVER = "#b91c1c"
    COLOR_RED_PRESSED = "#991b1b"
    COLOR_GRAY = "#1f2937"
    COLOR_GRAY_HOVER = "#374151"
    COLOR_GRAY_PRESSED = "#111827"

    def __init__(self):
        super().__init__()

        self._configure_window()

        self.running = False
        self.stop_event = threading.Event()
        self.click_thread: threading.Thread | None = None

        self.settings_lock = threading.Lock()
        self.settings = ClickerSettings()

        self.hotkey = keyboard.Key.f6
        self.hotkey_down = False
        self.waiting_for_hotkey = False

        self.cps_var = tk.StringVar(value=format_number(self.settings.cps))
        self.hold_var = tk.StringVar(value=format_number(self.settings.hold_ms))
        self.hotkey_var = tk.StringVar(value="F6")
        self.mouse_button_var = tk.StringVar(value=self.settings.mouse_button)
        self.mouse_canvas: tk.Canvas | None = None
        self.mouse_button_items: dict[str, list[int]] = {"left": [], "right": []}

        self._build_style()
        self._build_ui()
        self._start_keyboard_listener()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_window(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.title("Valheim Attack AutoClicker")
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.minsize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.resizable(False, False)
        self.configure(bg=self.COLOR_BG)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            ".",
            background=self.COLOR_BG,
            foreground=self.COLOR_TEXT,
            fieldbackground=self.COLOR_FIELD,
            bordercolor=self.COLOR_BORDER,
            lightcolor=self.COLOR_BORDER,
            darkcolor=self.COLOR_BORDER,
            troughcolor=self.COLOR_FIELD,
            focuscolor=self.COLOR_BLUE,
            font=("Segoe UI", 10),
        )

        style.configure("Root.TFrame", background=self.COLOR_BG)
        style.configure("Card.TFrame", background=self.COLOR_CARD, relief="flat")

        style.configure(
            "Title.TLabel",
            background=self.COLOR_BG,
            foreground="#f9fafb",
            font=("Segoe UI Semibold", 20),
        )

        style.configure(
            "Subtitle.TLabel",
            background=self.COLOR_BG,
            foreground=self.COLOR_MUTED,
            font=("Segoe UI", 10),
        )

        style.configure(
            "Card.TLabel",
            background=self.COLOR_CARD,
            foreground="#d1d5db",
            font=("Segoe UI", 10),
        )

        style.configure(
            "Value.TLabel",
            background=self.COLOR_CARD,
            foreground=self.COLOR_WHITE,
            font=("Segoe UI Semibold", 10),
        )

        style.configure(
            "TEntry",
            padding=8,
            borderwidth=1,
            relief="flat",
            foreground="#f9fafb",
            fieldbackground=self.COLOR_FIELD,
            insertcolor=self.COLOR_WHITE,
        )

        style.configure(
            "TButton",
            padding=(12, 8),
            background=self.COLOR_GRAY,
            foreground="#f9fafb",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "TButton",
            background=[("active", self.COLOR_GRAY_HOVER), ("pressed", self.COLOR_GRAY_PRESSED)],
        )

        style.configure(
            "Accent.TButton",
            padding=(14, 11),
            background=self.COLOR_BLUE,
            foreground=self.COLOR_WHITE,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.COLOR_BLUE_HOVER), ("pressed", self.COLOR_BLUE_PRESSED)],
        )

        style.configure(
            "Danger.TButton",
            padding=(14, 11),
            background=self.COLOR_RED,
            foreground=self.COLOR_WHITE,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", self.COLOR_RED_HOVER), ("pressed", self.COLOR_RED_PRESSED)],
        )

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=24)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Valheim AutoClicker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text='The "click" is: mouse down -> hold -> mouse up',
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        settings_card = ttk.Frame(root, style="Card.TFrame", padding=20)
        settings_card.pack(fill="x")
        settings_card.columnconfigure(0, weight=1)
        settings_card.columnconfigure(1, weight=1)

        ttk.Label(settings_card, text="CPS / Clicks per second", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        ttk.Entry(settings_card, textvariable=self.cps_var).grid(
            row=1, column=0, sticky="ew", padx=(0, 10)
        )

        ttk.Label(settings_card, text="Hold duration, ms", style="Card.TLabel").grid(
            row=0, column=1, sticky="w", pady=(0, 7)
        )
        ttk.Entry(settings_card, textvariable=self.hold_var).grid(
            row=1, column=1, sticky="ew", padx=(10, 0)
        )

        ttk.Label(settings_card, text="Mouse button", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(18, 7)
        )
        self.mouse_canvas = tk.Canvas(
            settings_card,
            width=300,
            height=290,
            bg=self.COLOR_CARD,
            highlightthickness=0,
        )
        self.mouse_canvas.grid(row=3, column=0, rowspan=3, sticky="w", padx=(0, 10))
        self.mouse_canvas.bind("<Button-1>", lambda _event: self._select_mouse_button("left"))
        self.mouse_canvas.bind("<Button-3>", lambda _event: self._select_mouse_button("right"))
        self._draw_mouse_selector()

        ttk.Label(settings_card, text="Activation key", style="Card.TLabel").grid(
            row=2, column=1, sticky="w", pady=(18, 7), padx=(10, 0)
        )
        hotkey_row = ttk.Frame(settings_card, style="Card.TFrame")
        hotkey_row.grid(row=3, column=1, sticky="ew", padx=(10, 0))
        hotkey_row.columnconfigure(1, weight=1)

        ttk.Label(hotkey_row, textvariable=self.hotkey_var, style="Value.TLabel", width=14).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(hotkey_row, text="Change", command=self._start_hotkey_capture).grid(
            row=0, column=1, sticky="ew", padx=(12, 0)
        )

        ttk.Button(settings_card, text="Apply Settings", command=self._apply_settings_from_ui).grid(
            row=4, column=1, sticky="ew", padx=(10, 0), pady=(18, 0)
        )

        self.toggle_button = ttk.Button(
            root,
            text="Enable",
            style="Accent.TButton",
            command=self.toggle_clicking,
        )
        self.toggle_button.pack(fill="x", pady=(18, 0))

    def _draw_mouse_selector(self) -> None:
        if self.mouse_canvas is None:
            return

        canvas = self.mouse_canvas
        canvas.delete("all")
        self.mouse_button_items = {"left": [], "right": []}

        outline = self.COLOR_BORDER
        body = "#0c1017"
        body_dark = "#070a0f"
        panel = "#141b26"
        panel_light = "#1e2938"
        inactive = "#18202d"
        inactive_top = "#263244"
        active = "#7f1d1d"
        active_top = "#991b1b"
        active_outline = "#ef4444"
        green = "#22c55e"
        green_dark = "#0f6b38"
        selected = self.mouse_button_var.get()

        canvas.create_oval(78, 255, 222, 276, fill="#05070b", outline="")
        canvas.create_polygon(
            150, 7, 183, 18, 212, 53, 232, 104, 245, 175, 228, 231, 198, 266, 163, 279, 137, 279, 102, 266, 72, 231, 55, 175, 68, 104, 88, 53, 117, 18,
            fill=body, outline=outline, width=3, smooth=True, splinesteps=32,
        )
        canvas.create_polygon(
            150, 23, 176, 31, 198, 61, 214, 109, 224, 171, 209, 221, 185, 249, 160, 260, 140, 260, 115, 249, 91, 221, 76, 171, 86, 109, 102, 61, 124, 31,
            fill=panel, outline="#202838", width=1, smooth=True, splinesteps=32,
        )

        left_fill = active if selected == "left" else inactive
        left_top = active_top if selected == "left" else inactive_top
        left_outline = active_outline if selected == "left" else outline
        right_fill = active if selected == "right" else inactive
        right_top = active_top if selected == "right" else inactive_top
        right_outline = active_outline if selected == "right" else outline

        if selected == "left":
            canvas.create_polygon(
                91, 27, 143, 5, 143, 112, 80, 129, 67, 90,
                fill="#450a0a", outline="", smooth=True, splinesteps=24,
            )
        else:
            canvas.create_polygon(
                157, 5, 209, 27, 233, 90, 220, 129, 157, 112,
                fill="#450a0a", outline="", smooth=True, splinesteps=24,
            )

        self.mouse_button_items["left"].append(
            canvas.create_polygon(
                91, 27, 143, 5, 143, 112, 80, 129, 67, 90,
                fill=left_fill, outline=left_outline, width=2, smooth=True, splinesteps=24,
            )
        )
        self.mouse_button_items["right"].append(
            canvas.create_polygon(
                157, 5, 209, 27, 233, 90, 220, 129, 157, 112,
                fill=right_fill, outline=right_outline, width=2, smooth=True, splinesteps=24,
            )
        )

        canvas.create_polygon(
            97, 33, 136, 17, 136, 50, 91, 68,
            fill=left_top, outline="", smooth=True, splinesteps=16,
        )
        canvas.create_polygon(
            164, 17, 203, 33, 209, 68, 164, 50,
            fill=right_top, outline="", smooth=True, splinesteps=16,
        )

        canvas.create_polygon(
            85, 134, 143, 116, 143, 258, 112, 247, 87, 217, 74, 170,
            fill="#101722", outline="#263244", width=2, smooth=True, splinesteps=18,
        )
        canvas.create_polygon(
            157, 116, 215, 134, 226, 170, 213, 217, 188, 247, 157, 258,
            fill="#101722", outline="#263244", width=2, smooth=True, splinesteps=18,
        )
        canvas.create_polygon(
            92, 143, 142, 128, 143, 155, 100, 169,
            fill=panel_light, outline="#334155", width=1, smooth=True, splinesteps=12,
        )
        canvas.create_polygon(
            158, 128, 208, 143, 200, 169, 157, 155,
            fill=panel_light, outline="#334155", width=1, smooth=True, splinesteps=12,
        )

        for x1, y1, x2, y2 in (
            (70, 136, 96, 119), (67, 146, 100, 125), (66, 156, 104, 132),
            (66, 166, 108, 139), (68, 176, 111, 148), (230, 136, 204, 119),
            (233, 146, 200, 125), (234, 156, 196, 132), (234, 166, 192, 139),
            (232, 176, 189, 148),
        ):
            canvas.create_line(x1, y1, x2, y2, fill="#475569", width=1)

        canvas.create_line(150, 7, 150, 120, fill="#030712", width=5)
        canvas.create_line(150, 8, 150, 120, fill=outline, width=2)
        canvas.create_line(75, 128, 225, 128, fill="#030712", width=4)
        canvas.create_line(83, 127, 217, 127, fill=outline, width=2)
        canvas.create_arc(82, 154, 218, 266, start=200, extent=140, style="arc", outline="#334155", width=2)
        canvas.create_oval(134, 36, 166, 95, fill=body_dark, outline=outline, width=2)
        canvas.create_rectangle(140, 42, 160, 83, fill="#111827", outline="#374151", width=1)
        canvas.create_rectangle(144, 45, 156, 79, fill=green_dark, outline=green, width=1)

        for y in range(49, 78, 5):
            canvas.create_line(146, y, 154, y, fill="#86efac", width=1)

        canvas.create_rectangle(138, 98, 162, 124, fill=body_dark, outline="#334155", width=2)
        canvas.create_rectangle(142, 101, 158, 115, fill="#1f2937", outline="#4b5563", width=1)
        canvas.create_line(95, 35, 132, 20, fill="#334155", width=1)
        canvas.create_line(168, 20, 205, 35, fill="#334155", width=1)
        canvas.create_text(113, 80, text="LMB", fill=self.COLOR_TEXT, font=("Segoe UI Semibold", 10))
        canvas.create_text(187, 80, text="RMB", fill=self.COLOR_TEXT, font=("Segoe UI Semibold", 10))
        canvas.create_arc(124, 214, 155, 246, start=25, extent=250, style="arc", outline=green, width=3)
        canvas.create_arc(145, 213, 176, 246, start=-95, extent=250, style="arc", outline=green, width=3)
        canvas.create_arc(135, 198, 165, 229, start=145, extent=250, style="arc", outline=green, width=3)
        canvas.create_oval(146, 220, 154, 228, fill=green, outline="")
        canvas.create_text(
            150,
            276,
            text="selected: " + ("LMB" if selected == "left" else "RMB"),
            fill=self.COLOR_MUTED,
            font=("Segoe UI", 9),
        )

    def _select_mouse_button(self, mouse_button: str) -> None:
        if mouse_button not in MOUSE_BUTTON_EVENTS:
            return

        self.mouse_button_var.set(mouse_button)
        with self.settings_lock:
            self.settings = ClickerSettings(
                cps=self.settings.cps,
                hold_ms=self.settings.hold_ms,
                mouse_button=mouse_button,
            )
        self._draw_mouse_selector()

    def _apply_settings_from_ui(self, update_canvas: bool = True) -> bool:
        try:
            new_settings = ClickerSettings.from_strings(
                self.cps_var.get(),
                self.hold_var.get(),
                self.mouse_button_var.get(),
            )
        except ValueError:
            messagebox.showerror("Error", "CPS and hold duration must be valid numbers.")
            return False

        with self.settings_lock:
            self.settings = new_settings

        self.cps_var.set(format_number(new_settings.cps))
        self.hold_var.set(format_number(new_settings.hold_ms))
        self.mouse_button_var.set(new_settings.mouse_button)
        if update_canvas:
            self._draw_mouse_selector()
        return True

    def _get_settings_snapshot(self) -> ClickerSettings:
        with self.settings_lock:
            return ClickerSettings(
                cps=self.settings.cps,
                hold_ms=self.settings.hold_ms,
                mouse_button=self.settings.mouse_button,
            )

    def _start_keyboard_listener(self) -> None:
        self.listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.listener.daemon = True
        self.listener.start()

    def _start_hotkey_capture(self) -> None:
        if self.running:
            messagebox.showinfo("Hotkey", "Disable the autoclicker before changing the key.")
            return

        self.waiting_for_hotkey = True
        self.hotkey_var.set("Press a key...")

    def _set_hotkey(self, key) -> None:
        self.hotkey = key
        self.hotkey_down = False
        self.waiting_for_hotkey = False
        self.hotkey_var.set(self._key_to_text(key))

    def _cancel_hotkey_capture(self) -> None:
        self.waiting_for_hotkey = False
        self.hotkey_var.set(self._key_to_text(self.hotkey))

    @staticmethod
    def _key_to_text(key) -> str:
        if isinstance(key, keyboard.KeyCode):
            if key.char:
                return key.char.upper()
            if key.vk:
                return f"VK_{key.vk}"
            return "UNKNOWN"

        name = getattr(key, "name", str(key))
        return name.upper().replace("_", " ")

    def _on_key_press(self, key) -> None:
        if self.waiting_for_hotkey:
            if key == keyboard.Key.esc:
                self.after(0, self._cancel_hotkey_capture)
            else:
                self.after(0, lambda captured_key=key: self._set_hotkey(captured_key))
            return

        if key == self.hotkey and not self.hotkey_down:
            self.hotkey_down = True
            self.after(0, self.toggle_clicking)

    def _on_key_release(self, key) -> None:
        if key == self.hotkey:
            self.hotkey_down = False

    def toggle_clicking(self) -> None:
        if self.running:
            self.stop_clicking()
        else:
            self.start_clicking()

    def start_clicking(self) -> None:
        if not self._apply_settings_from_ui():
            return

        if self.running:
            return

        self.running = True
        self.stop_event.clear()
        self._set_running_ui(True)

        self.click_thread = threading.Thread(
            target=self._click_loop,
            name="ValheimClickThread",
            daemon=True,
        )
        self.click_thread.start()

    def stop_clicking(self) -> None:
        if not self.running:
            return

        self.running = False
        self.stop_event.set()
        self._set_running_ui(False)

    def _set_running_ui(self, is_running: bool) -> None:
        if is_running:
            self.toggle_button.configure(text="Disable", style="Danger.TButton")
        else:
            self.toggle_button.configure(text="Enable", style="Accent.TButton")

    def _click_loop(self) -> None:
        next_click = time.perf_counter()

        while not self.stop_event.is_set():
            settings = self._get_settings_snapshot()

            interval = 1.0 / max(settings.cps, ClickerSettings.MIN_CPS)

            hold_seconds = min(settings.hold_ms / 1000.0, interval * 0.75)

            send_mouse_click(settings.mouse_button, hold_seconds)

            next_click += interval
            sleep_time = next_click - time.perf_counter()

            if sleep_time > 0:
                self.stop_event.wait(sleep_time)
            else:
                next_click = time.perf_counter()

    def _on_close(self) -> None:
        self.stop_clicking()

        try:
            self.listener.stop()
        except Exception:
            pass

        self.destroy()


if __name__ == "__main__":
    app = ValheimAutoClicker()
    app.mainloop()