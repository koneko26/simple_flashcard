import csv
import os
import random
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox


def _enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _set_taskbar_app_id():
    """Detach the Windows taskbar grouping from python.exe so our icon shows correctly."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("flashcards.app.1")
    except Exception:
        pass


def _apply_app_icon(root):
    try:
        icon = tk.PhotoImage(width=64, height=64)
        icon.put("#2f6df6", to=(0, 0, 64, 64))
        # White "F" letter for Flashcards
        icon.put("white", to=(20, 14, 28, 50))   # vertical bar
        icon.put("white", to=(20, 14, 46, 22))   # top arm
        icon.put("white", to=(20, 28, 40, 34))   # middle arm
        root.iconphoto(True, icon)
        root._app_icon = icon  # keep a reference so it isn't garbage-collected
    except Exception:
        pass


def _to_colorref(hex_color):
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (b << 16) | (g << 8) | r


def _style_title_bar(root, bg_hex, text_hex=None):
    """Windows 11 22H2+: tint the OS-drawn title bar via the DWM API."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.GetParent.argtypes = [wintypes.HWND]
        ctypes.windll.user32.GetParent.restype = wintypes.HWND
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        dwm = ctypes.windll.dwmapi
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36
        bg = ctypes.c_int32(_to_colorref(bg_hex))
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR,
                                  ctypes.byref(bg), ctypes.sizeof(bg))
        if text_hex:
            tc = ctypes.c_int32(_to_colorref(text_hex))
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR,
                                      ctypes.byref(tc), ctypes.sizeof(tc))
    except Exception:
        pass

COLORS = {
    "bg": "#eef2f8",
    "card_bg": "#ffffff",
    "card_border": "#e3e8f1",
    "primary": "#2f6df6",
    "primary_soft": "#eaf0ff",
    "primary_deep": "#1d4fd7",
    "text": "#1f2937",
    "text_strong": "#1c1f2b",
    "text_sub": "#6b7280",
    "text_mute": "#9aa3b2",
    "border_soft": "#e3e8f1",
    "chip_bg": "#ffffff",
    "chip_active_bg": "#eaf0ff",
    "chip_active_hover": "#dde6ff",
    "chip_hover": "#f3f5fa",
    "btn_secondary": "#ffffff",
    "btn_secondary_hover": "#f3f5fa",
}

FONT_UI = "Meiryo UI"
FONT_CARD = "Meiryo UI"
COMPACT_W = 400
COMPACT_H = 540

DISPLAY_MODES = ["Unlearned", "Learned", "All"]


def _rounded_pts(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _parent_bg(parent):
    if isinstance(parent, RoundedFrame):
        return parent.fill_color
    try:
        return parent.cget("bg")
    except tk.TclError:
        return "#ffffff"


class RoundedFrame(tk.Canvas):
    def __init__(self, parent, *, radius=16, fill="#ffffff",
                 outline="", outline_width=0, **kwargs):
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=_parent_bg(parent), **kwargs)
        self.radius = radius
        self.fill_color = fill
        self.outline = outline
        self.outline_width = outline_width
        self._bg_id = None
        self.bind("<Configure>", self._redraw_bg, add="+")

    def _redraw_bg(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        if self._bg_id is not None:
            self.delete(self._bg_id)
        r = max(2, min(self.radius, w // 2, h // 2))
        self._bg_id = self.create_polygon(
            _rounded_pts(0, 0, w, h, r),
            smooth=True, fill=self.fill_color,
            outline=self.outline if self.outline_width else "",
            width=self.outline_width,
        )
        self.tag_lower(self._bg_id)


class RoundedButton(tk.Canvas):
    def __init__(self, parent, *, radius=12, fill="#ffffff", hover_fill=None,
                 text="", fg="#000000", font=None,
                 command=None, on_click=None,
                 height=None, width=None,
                 auto_width=False, h_padding=14):
        kwargs = {}
        if height is not None:
            kwargs["height"] = height
        if width is not None:
            kwargs["width"] = width
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=_parent_bg(parent), **kwargs)
        self.radius = radius
        self._normal_fill = fill
        self._hover_fill = hover_fill if hover_fill is not None else fill
        self._current_fill = fill
        self.text = text
        self.fg = fg
        self.font = font
        self.command = command
        self.auto_width = auto_width
        self.h_padding = h_padding
        self.bind("<Configure>", self._redraw)
        if command or on_click:
            self.configure(cursor="hand2")
            if on_click:
                self.bind("<Button-1>", on_click)
            elif command:
                self.bind("<Button-1>", lambda _e: self.command())
        if self._hover_fill != self._normal_fill:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
        if self.auto_width and self.text:
            self._fit_to_text()

    def _fit_to_text(self):
        if not self.auto_width or not self.text:
            return
        try:
            tid = self.create_text(0, 0, text=self.text, font=self.font, anchor="nw")
            bbox = self.bbox(tid)
            self.delete(tid)
            if bbox:
                w = (bbox[2] - bbox[0]) + self.h_padding * 2
                self.configure(width=max(40, w))
        except Exception:
            pass

    def _redraw(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        self.delete("all")
        r = max(2, min(self.radius, w // 2, h // 2))
        self.create_polygon(
            _rounded_pts(0, 0, w, h, r),
            smooth=True, fill=self._current_fill, outline="",
        )
        if self.text:
            self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=self.font)

    def _on_enter(self, _e):
        self._current_fill = self._hover_fill
        self._redraw()

    def _on_leave(self, _e):
        self._current_fill = self._normal_fill
        self._redraw()

    def set_text(self, text):
        self.text = text
        if self.auto_width:
            self._fit_to_text()
        self._redraw()


class HelpDialog(tk.Toplevel):
    """Modeless help window styled to match the app palette."""
    def __init__(self, parent_root):
        super().__init__(parent_root)
        self.transient(parent_root)
        self.title("How to use")
        self.configure(bg=COLORS["card_bg"])
        self.resizable(False, False)

        body = tk.Frame(self, bg=COLORS["card_bg"])
        body.pack(padx=28, pady=24)

        tk.Label(
            body, text="How to use Flashcards",
            font=(FONT_UI, 14, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["text_strong"],
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            body, text="Quick reference for getting around.",
            font=(FONT_UI, 9),
            bg=COLORS["card_bg"], fg=COLORS["text_sub"],
        ).pack(anchor="w", pady=(0, 14))

        sections = [
            ("Card",
             "•  Click the card (or press Space) to flip JP ↔ EN"),
            ("Move through cards",
             "•  ← / →            Previous / Next card\n"
             "•  ⏎ Enter           Mark current card as learned"),
            ("Filter",
             "•  Click the chips at the top to filter by category\n"
             "    or by Unlearned / Learned / All"),
            ("Window",
             "•  ↘     Dock to small size at the bottom-right corner\n"
             "•  Load  Open a CSV file"),
            ("CSV columns",
             "english, japanese, category, active, learned\n"
             "•  active  = 1 to include the card, 0 to skip\n"
             "•  learned = 1 if memorized (auto-saved on Got it)"),
            ("Shortcuts",
             "•  F1     Show this help"),
        ]

        for heading, content in sections:
            tk.Label(
                body, text=heading,
                font=(FONT_UI, 10, "bold"),
                bg=COLORS["card_bg"], fg=COLORS["primary"],
            ).pack(anchor="w", pady=(2, 4))
            tk.Label(
                body, text=content,
                font=(FONT_UI, 9),
                bg=COLORS["card_bg"], fg=COLORS["text"],
                justify="left",
            ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            body, text="Press Esc to close",
            font=(FONT_UI, 8),
            bg=COLORS["card_bg"], fg=COLORS["text_mute"],
        ).pack(anchor="w", pady=(6, 0))

        self.update_idletasks()
        try:
            px, py = parent_root.winfo_rootx(), parent_root.winfo_rooty()
            pw, ph = parent_root.winfo_width(), parent_root.winfo_height()
            x = px + (pw - self.winfo_width()) // 2
            y = py + (ph - self.winfo_height()) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.bind("<Escape>", lambda _e: self.destroy())
        self.focus_force()


class StyledPopup(tk.Toplevel):
    """Rounded borderless popup. Items are clickable rows; clicks outside dismiss it."""
    def __init__(self, parent_root, items, on_select, anchor_widget, *, current=None):
        super().__init__(parent_root)
        self.parent_root = parent_root
        self.on_select = on_select

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLORS["bg"])

        item_font = (FONT_UI, 10)
        max_text_w = self._measure_max_text(items, item_font)
        item_w = max(120, max_text_w + 32)
        item_h = 34
        gap = 2
        margin = 8
        outer = 4

        canvas_w = item_w + margin * 2
        canvas_h = len(items) * item_h + max(0, len(items) - 1) * gap + margin * 2

        body = RoundedFrame(
            self, radius=14, fill=COLORS["card_bg"],
            outline=COLORS["card_border"], outline_width=1,
            width=canvas_w, height=canvas_h,
        )
        body.pack(padx=outer, pady=outer)
        body.pack_propagate(False)

        for i, label in enumerate(items):
            y = margin + i * (item_h + gap)
            is_current = (label == current)
            item = RoundedButton(
                body, text=label,
                radius=9,
                fill=(COLORS["primary_soft"] if is_current else COLORS["card_bg"]),
                hover_fill=COLORS["primary_soft"],
                fg=(COLORS["primary_deep"] if is_current else COLORS["text"]),
                font=item_font,
                height=item_h, width=item_w,
                command=lambda l=label: self._choose(l),
            )
            item.place(x=margin, y=y)

        self.update_idletasks()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 6
        screen_w = self.winfo_screenwidth()
        if x + self.winfo_reqwidth() > screen_w - 8:
            x = screen_w - self.winfo_reqwidth() - 8
        self.geometry(f"+{int(x)}+{int(y)}")

        self._outside_binding = self.parent_root.bind(
            "<Button-1>", self._maybe_dismiss, add="+"
        )
        self.bind("<Escape>", lambda _e: self._dismiss())
        self.bind("<Destroy>", self._cleanup, add="+")
        self.focus_force()

    @staticmethod
    def _measure_max_text(items, font):
        tmp = tk.Canvas()
        max_w = 0
        for label in items:
            tid = tmp.create_text(0, 0, text=label, font=font, anchor="nw")
            bbox = tmp.bbox(tid)
            tmp.delete(tid)
            if bbox:
                max_w = max(max_w, bbox[2] - bbox[0])
        tmp.destroy()
        return max_w

    def _maybe_dismiss(self, event):
        try:
            x1, y1 = self.winfo_rootx(), self.winfo_rooty()
            x2, y2 = x1 + self.winfo_width(), y1 + self.winfo_height()
            if not (x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2):
                self._dismiss()
        except Exception:
            self._dismiss()

    def _cleanup(self, _e):
        try:
            self.parent_root.unbind("<Button-1>", self._outside_binding)
        except Exception:
            pass

    def _dismiss(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _choose(self, label):
        try:
            self.on_select(label)
        finally:
            self._dismiss()


class FlashcardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Flashcards")
        self.root.geometry("420x560")
        self.root.minsize(280, 360)
        self.root.configure(bg=COLORS["bg"])

        self.csv_path = None
        self.cards = []
        self.queue = []
        self.index = 0
        self.is_japanese = True
        self.category_filter = "All"
        self.display_mode = "Unlearned"
        self._compact = False

        self._build_ui()
        self._bind_keys()
        self.root.bind("<Configure>", self._on_root_configure)

        default_csv = os.path.join(self._script_dir(), "cards.csv")
        if os.path.exists(default_csv):
            self.load_csv(default_csv)

    @staticmethod
    def _script_dir():
        if hasattr(sys, "frozen"):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _build_ui(self):
        # ─── Top bar ───
        self.topbar = tk.Frame(self.root, bg=COLORS["bg"])
        self.topbar.pack(fill="x", padx=16, pady=(16, 10))

        self.chips_frame = tk.Frame(self.topbar, bg=COLORS["bg"])
        self.chips_frame.pack(side="left")

        self.category_chip = RoundedButton(
            self.chips_frame, text="All categories  ▾",
            radius=14, fill=COLORS["chip_active_bg"], hover_fill=COLORS["chip_active_hover"],
            fg=COLORS["primary_deep"], font=(FONT_UI, 9),
            on_click=self._show_category_menu,
            height=30, auto_width=True, h_padding=14,
        )
        self.category_chip.pack(side="left", padx=(0, 6))

        self.mode_chip = RoundedButton(
            self.chips_frame, text="Unlearned  ▾",
            radius=14, fill=COLORS["chip_bg"], hover_fill=COLORS["chip_hover"],
            fg=COLORS["text_sub"], font=(FONT_UI, 9),
            on_click=self._show_mode_menu,
            height=30, auto_width=True, h_padding=14,
        )
        self.mode_chip.pack(side="left")

        self.load_btn = RoundedButton(
            self.topbar, text="Load",
            radius=12, fill=COLORS["chip_bg"], hover_fill=COLORS["chip_hover"],
            fg=COLORS["text_sub"], font=(FONT_UI, 9),
            command=self.choose_csv,
            width=58, height=30,
        )
        self.load_btn.pack(side="right")

        self.reset_btn = RoundedButton(
            self.topbar, text="Reset",
            radius=12, fill=COLORS["chip_bg"], hover_fill=COLORS["chip_hover"],
            fg=COLORS["text_sub"], font=(FONT_UI, 9),
            command=self.reset_learned,
            width=58, height=30,
        )
        self.reset_btn.pack(side="right", padx=(0, 6))

        self.snap_btn = RoundedButton(
            self.topbar, text="↘",
            radius=12, fill=COLORS["chip_bg"], hover_fill=COLORS["chip_hover"],
            fg=COLORS["text_sub"], font=(FONT_UI, 12),
            command=self.snap_to_corner,
            width=36, height=30,
        )
        self.snap_btn.pack(side="right", padx=(0, 6))

        self.help_btn = RoundedButton(
            self.topbar, text="?",
            radius=12, fill=COLORS["chip_bg"], hover_fill=COLORS["chip_hover"],
            fg=COLORS["text_sub"], font=(FONT_UI, 11, "bold"),
            command=self.show_help,
            width=32, height=30,
        )
        self.help_btn.pack(side="right", padx=(0, 6))

        # ─── Card area ───
        self.card_area = tk.Frame(self.root, bg=COLORS["bg"])
        self.card_area.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self.card = RoundedFrame(self.card_area, radius=20, fill=COLORS["card_bg"],
                                  outline=COLORS["card_border"], outline_width=1)
        self.card.pack(fill="both", expand=True)
        self.card.configure(cursor="hand2")
        self.card.bind("<Configure>", self._on_card_resize, add="+")
        self.card.bind("<Button-1>", lambda _e: self.flip())

        self.card_tag = RoundedButton(
            self.card, text="",
            radius=10, fill=COLORS["primary_soft"],
            fg=COLORS["primary"], font=(FONT_UI, 8, "bold"),
            height=22, auto_width=True, h_padding=10,
            on_click=lambda _e: self.flip(),
        )

        self.card_index = tk.Label(
            self.card, text="", font=(FONT_UI, 9),
            bg=COLORS["card_bg"], fg=COLORS["text_mute"],
        )
        self.card_index.place(relx=1.0, x=-18, y=18, anchor="ne")

        self.card_text = tk.Label(
            self.card, text="Click Load to open a CSV",
            font=(FONT_CARD, 18), bg=COLORS["card_bg"], fg=COLORS["text"],
            wraplength=320, justify="center",
        )
        self.card_text.place(relx=0.5, rely=0.5, anchor="center")

        self.card_hint = tk.Label(
            self.card, text="tap to flip",
            font=(FONT_UI, 8), bg=COLORS["card_bg"], fg=COLORS["text_mute"],
        )
        self.card_hint.place(relx=0.5, rely=1.0, y=-16, anchor="s")

        for w in (self.card_text, self.card_index, self.card_hint):
            w.bind("<Button-1>", lambda _e: self.flip())

        # ─── Controls ───
        self.controls = tk.Frame(self.root, bg=COLORS["bg"])
        self.controls.pack(fill="x", padx=16, pady=(0, 10))

        self.btn_prev = RoundedButton(
            self.controls, text="← Prev",
            radius=14, fill=COLORS["btn_secondary"], hover_fill=COLORS["btn_secondary_hover"],
            fg=COLORS["text"], font=(FONT_UI, 10, "bold"),
            command=self.prev_card, height=46, width=1,
        )
        self.btn_prev.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_got = RoundedButton(
            self.controls, text="✓ Got it",
            radius=14, fill=COLORS["primary"], hover_fill=COLORS["primary_deep"],
            fg="white", font=(FONT_UI, 10, "bold"),
            command=self.mark_learned, height=46, width=1,
        )
        self.btn_got.pack(side="left", expand=True, fill="x", padx=6)

        self.btn_next = RoundedButton(
            self.controls, text="Next →",
            radius=14, fill=COLORS["btn_secondary"], hover_fill=COLORS["btn_secondary_hover"],
            fg=COLORS["text"], font=(FONT_UI, 10, "bold"),
            command=self.next_card, height=46, width=1,
        )
        self.btn_next.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # ─── Footer ───
        self.footer = tk.Frame(self.root, bg=COLORS["bg"])
        self.footer.pack(fill="x", padx=16, pady=(0, 16))

        meta = tk.Frame(self.footer, bg=COLORS["bg"])
        meta.pack(fill="x")

        self.queue_label = tk.Label(
            meta, text="0 of 0 in queue",
            font=(FONT_UI, 9), bg=COLORS["bg"], fg=COLORS["text_sub"],
        )
        self.queue_label.pack(side="left")

        self.learned_label = tk.Label(
            meta, text="0 / 0 learned",
            font=(FONT_UI, 9), bg=COLORS["bg"], fg=COLORS["text_sub"],
        )
        self.learned_label.pack(side="right")

        bar_outer = tk.Frame(self.footer, bg=COLORS["bg"], height=8)
        bar_outer.pack(fill="x", pady=(10, 10))
        bar_outer.pack_propagate(False)
        self.progress_bar = RoundedFrame(bar_outer, radius=3, fill=COLORS["border_soft"])
        self.progress_bar.pack(fill="both", expand=True)
        self.progress_fill = RoundedFrame(self.progress_bar, radius=3, fill=COLORS["primary"])
        self.progress_fill.place(x=0, y=0, relheight=1, relwidth=0)

        tk.Label(
            self.footer,
            text="←  Prev      ␣  Flip      →  Next      ⏎  Got it",
            font=(FONT_UI, 8), bg=COLORS["bg"], fg=COLORS["text_mute"],
        ).pack(anchor="center")

    def _bind_keys(self):
        self.root.bind("<Left>", lambda _e: self.prev_card())
        self.root.bind("<Right>", lambda _e: self.next_card())
        self.root.bind("<space>", lambda _e: self.flip())
        self.root.bind("<Return>", lambda _e: self.mark_learned())
        self.root.bind("<F1>", lambda _e: self.show_help())

    def _on_card_resize(self, event):
        self.card_text.config(wraplength=max(160, event.width - 50))

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        compact = event.width < COMPACT_W or event.height < COMPACT_H
        if compact != self._compact:
            self._compact = compact
            self._apply_compact()

    def _apply_compact(self):
        if self._compact:
            self.footer.pack_forget()
            self.chips_frame.pack_forget()
            self.load_btn.pack_forget()
            self.snap_btn.pack_forget()
            self.help_btn.pack_forget()
            self.topbar.pack_forget()
            self.card_area.pack_configure(padx=8, pady=(8, 8))
            self.controls.pack_configure(padx=8, pady=(0, 8))
            self.card_hint.place_forget()
        else:
            self.topbar.pack(fill="x", padx=16, pady=(16, 10),
                             before=self.card_area)
            self.chips_frame.pack(side="left")
            self.load_btn.pack(side="right")
            self.reset_btn.pack(side="right", padx=(0, 6))
            self.snap_btn.pack(side="right", padx=(0, 6))
            self.help_btn.pack(side="right", padx=(0, 6))
            self.card_area.pack_configure(padx=16, pady=(0, 12))
            self.controls.pack_configure(padx=16, pady=(0, 10))
            self.footer.pack(fill="x", padx=16, pady=(0, 16))
            self.card_hint.place(relx=0.5, rely=1.0, y=-16, anchor="s")

    def _show_category_menu(self, _event):
        if not self.cards:
            return
        items = ["All categories"]
        items.extend(sorted({c["category"] for c in self.cards if c["category"]}))
        current_label = ("All categories" if self.category_filter == "All"
                         else self.category_filter)
        StyledPopup(self.root, items, self._select_category_label,
                    self.category_chip, current=current_label)

    def _show_mode_menu(self, _event):
        StyledPopup(self.root, list(DISPLAY_MODES), self._set_mode,
                    self.mode_chip, current=self.display_mode)

    def _select_category_label(self, label):
        cat = "All" if label == "All categories" else label
        self.category_filter = cat
        self.category_chip.set_text(f"{label}  ▾")
        self._rebuild_queue()

    def _set_mode(self, mode):
        self.display_mode = mode
        self.mode_chip.set_text(f"{mode}  ▾")
        self._rebuild_queue()

    def show_help(self):
        HelpDialog(self.root)

    def snap_to_corner(self, small_w=320, small_h=420, margin=16):
        """Resize to a small window and dock at the bottom-right of the working area."""
        # Leave maximized/iconic states first; geometry() is ignored otherwise.
        try:
            state = self.root.state()
            if state != "normal":
                self.root.state("normal")
        except Exception:
            pass
        self.root.update_idletasks()

        left, top, right, bottom = self._screen_workarea()
        x = max(left, right - small_w - margin)
        y = max(top, bottom - small_h - margin)
        self.root.geometry(f"{small_w}x{small_h}+{int(x)}+{int(y)}")

    def _screen_workarea(self):
        """Return (left, top, right, bottom) of the usable monitor area (excludes taskbar)."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG),
                    ]

                user32 = ctypes.windll.user32
                user32.SystemParametersInfoW.argtypes = [
                    wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT,
                ]
                user32.SystemParametersInfoW.restype = wintypes.BOOL

                rect = RECT()
                ok = user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
                if ok and rect.right > rect.left and rect.bottom > rect.top:
                    return rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                pass
        # Fallback: assume full screen minus a typical taskbar
        w = self.root.winfo_screenwidth()
        h = self.root.winfo_screenheight()
        return 0, 0, w, max(0, h - 48)

    def choose_csv(self):
        path = filedialog.askopenfilename(
            title="Select CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.load_csv(path)

    def load_csv(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                cards = []
                for row in reader:
                    cards.append({
                        "english": (row.get("english") or "").strip(),
                        "japanese": (row.get("japanese") or "").strip(),
                        "category": (row.get("category") or "").strip(),
                        "active": (row.get("active") or "1").strip() == "1",
                        "learned": (row.get("learned") or "0").strip() == "1",
                    })
            self.cards = cards
            self.csv_path = path
            self._rebuild_queue()
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load CSV:\n{e}")

    def _rebuild_queue(self):
        pool = [c for c in self.cards if c["active"]]
        if self.category_filter != "All":
            pool = [c for c in pool if c["category"] == self.category_filter]
        if self.display_mode == "Unlearned":
            pool = [c for c in pool if not c["learned"]]
        elif self.display_mode == "Learned":
            pool = [c for c in pool if c["learned"]]
        random.shuffle(pool)
        self.queue = pool
        self.index = 0
        self.is_japanese = True
        self._render()

    def _render(self):
        if not self.queue:
            self.card_text.config(text="No cards to show")
            self.card_tag.place_forget()
            self.card_index.config(text="")
            self._update_progress()
            return
        card = self.queue[self.index]
        self.card_text.config(text=card["japanese"] if self.is_japanese else card["english"])
        if card["category"]:
            self.card_tag.set_text(card["category"].upper())
            self.card_tag.place(x=18, y=16)
        else:
            self.card_tag.place_forget()
        total = len(self.queue)
        self.card_index.config(text=f"{self.index + 1:02d} / {total:02d}")
        self._update_progress()

    def _update_progress(self):
        active = [c for c in self.cards if c["active"]]
        learned = sum(1 for c in active if c["learned"])
        total = len(active)
        qtotal = len(self.queue)
        qpos = self.index + 1 if self.queue else 0
        self.queue_label.config(text=f"{qpos} of {qtotal} in queue")
        self.learned_label.config(text=f"{learned} / {total} learned")
        ratio = (self.index + 1) / qtotal if qtotal > 0 else 0
        self.progress_fill.place_configure(relwidth=ratio)

    def flip(self):
        if not self.queue:
            return
        self.is_japanese = not self.is_japanese
        self._render()

    def next_card(self):
        if not self.queue:
            return
        self.index = (self.index + 1) % len(self.queue)
        self.is_japanese = True
        self._render()

    def prev_card(self):
        if not self.queue:
            return
        self.index = (self.index - 1) % len(self.queue)
        self.is_japanese = True
        self._render()

    def mark_learned(self):
        if not self.queue:
            return
        self.queue[self.index]["learned"] = True
        self._save_csv()
        if self.display_mode == "Unlearned":
            del self.queue[self.index]
            if not self.queue:
                self.is_japanese = True
                self._render()
                return
            self.index = self.index % len(self.queue)
            self.is_japanese = True
            self._render()
        else:
            self.next_card()

    def reset_learned(self):
        if not self.cards:
            return
        if self.category_filter == "All":
            targets = [c for c in self.cards if c["active"] and c["learned"]]
            label = "all learned cards"
        else:
            targets = [c for c in self.cards
                       if c["active"] and c["learned"] and c["category"] == self.category_filter]
            label = f'learned cards in "{self.category_filter}"'
        if not targets:
            messagebox.showinfo("Reset", f"No {label} to reset.")
            return
        if not messagebox.askyesno("Reset learned",
                                   f"Reset {len(targets)} {label} to unlearned?"):
            return
        for c in targets:
            c["learned"] = False
        self._save_csv()
        self._rebuild_queue()

    def _save_csv(self):
        if not self.csv_path:
            return
        try:
            shutil.copy2(self.csv_path, self.csv_path + ".bak")
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["english", "japanese", "category", "active", "learned"]
                )
                writer.writeheader()
                for c in self.cards:
                    writer.writerow({
                        "english": c["english"],
                        "japanese": c["japanese"],
                        "category": c["category"],
                        "active": "1" if c["active"] else "0",
                        "learned": "1" if c["learned"] else "0",
                    })
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save CSV:\n{e}")


def main():
    _enable_dpi_awareness()
    _set_taskbar_app_id()
    root = tk.Tk()
    try:
        scaling = root.winfo_fpixels("1i") / 72.0
        if scaling > 0:
            root.tk.call("tk", "scaling", scaling)
    except Exception:
        pass
    try:
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=FONT_UI, size=10)
    except Exception:
        pass
    _apply_app_icon(root)
    root.after(80, lambda: _style_title_bar(root, COLORS["bg"], COLORS["text"]))
    FlashcardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
