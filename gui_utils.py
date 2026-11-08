# -*- coding: utf-8 -*-

import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable


def _enable_windows_dpi_awareness():
    """Let Tk use real screen pixels when CloudCompare runs on scaled displays."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _fit_window_to_screen(window, preferred_width=1160, preferred_height=650):
    """Choose a compact initial size without exceeding the work area."""
    window.update_idletasks()
    screen_w = max(640, window.winfo_screenwidth())
    screen_h = max(480, window.winfo_screenheight())
    width = min(preferred_width, max(640, int(screen_w * 0.90)))
    height = min(preferred_height, max(480, int(screen_h * 0.85)))
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    window.geometry("{}x{}+{}+{}".format(width, height, x, y))
    window.minsize(min(900, width), min(350, height))


class DSEToolTip:
    def __init__(self, widget, text_callback):
        self.widget = widget
        self.text_callback = text_callback
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event=None):
        self.hide()
        text = self.text_callback()
        if not text:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        # Keep the tooltip above both the DSE window and CloudCompare.
        try:
            self.tip.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.tip.transient(self.widget.winfo_toplevel())
        except Exception:
            pass

        label = tk.Label(
            self.tip, text=text, justify=tk.LEFT, relief=tk.SOLID,
            borderwidth=1, background="#fffbe6", foreground="#202124",
            wraplength=430, padx=9, pady=7
        )
        label.pack()
        self.tip.update_idletasks()

        tip_width = self.tip.winfo_reqwidth()
        tip_height = self.tip.winfo_reqheight()
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        widget_x = self.widget.winfo_rootx()
        widget_y = self.widget.winfo_rooty()
        widget_height = self.widget.winfo_height()

        # Prefer the right side. If it does not fit, use left, then below/above.
        candidates = [
            (widget_x + self.widget.winfo_width() + 10, widget_y),
            (widget_x - tip_width - 10, widget_y),
            (widget_x + 10, widget_y + widget_height + 8),
            (widget_x + 10, widget_y - tip_height - 8),
        ]
        x, y = candidates[-1]
        for candidate_x, candidate_y in candidates:
            if (8 <= candidate_x <= screen_width - tip_width - 8 and
                    8 <= candidate_y <= screen_height - tip_height - 8):
                x, y = candidate_x, candidate_y
                break
        x = max(8, min(x, screen_width - tip_width - 8))
        y = max(8, min(y, screen_height - tip_height - 8))
        self.tip.wm_geometry(f"+{x}+{y}")

        # Windows occasionally places overrideredirect windows behind their
        # owner. Reasserting topmost after mapping fixes that z-order issue.
        self.tip.deiconify()
        self.tip.lift()
        try:
            self.tip.attributes("-topmost", True)
        except Exception:
            pass
        self.tip.after_idle(self._raise_tip)

    def _raise_tip(self):
        if self.tip is None:
            return
        try:
            self.tip.lift()
            self.tip.attributes("-topmost", True)
        except Exception:
            pass

    def hide(self, event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class _GraphicUtilitiesMixin:
    root: tk.Misc
    tr: Callable[..., str]

    def _help_text_for_widget(self, widget):
        """Return accurate contextual help, including dynamically built tools."""
        try:
            text = str(widget.cget("text")).strip()
        except Exception:
            text = ""

        if text:
            translated = self.tr(text, default=None)
            if translated and translated != text:
                return translated

        # Entries and comboboxes inherit the explanation of their associated label.
        if widget.winfo_class() in ("Entry", "TEntry", "Spinbox", "TCombobox"):
            try:
                siblings = widget.master.winfo_children()
                label_texts = []
                for sibling in siblings:
                    if sibling is widget:
                        continue
                    if sibling.winfo_class() in ("Label", "TLabel"):
                        candidate = str(sibling.cget("text")).strip()
                        if candidate:
                            label_texts.append(candidate)
                for candidate in label_texts:
                    translated = self.tr(candidate, default=None)
                    if translated and translated != candidate:
                        return translated
            except Exception:
                pass
            return self.tr("tip.editable_param")
        if widget.winfo_class() == "Treeview":
            return self.tr("tip.pole_table")
        if widget.winfo_class() in ("Button", "TButton"):
            return self.tr("tip.action_button")
        return text

    def _install_context_help_recursive(self, widget):
        """Attach help to every visible interactive widget, including dialogs."""
        interactive = {"Button", "TButton", "Entry", "TEntry", "Spinbox",
                       "TCombobox", "Checkbutton", "TCheckbutton", "Treeview",
                       "Listbox", "Scale", "TScale", "Label", "TLabel"}
        try:
            if widget.winfo_class() in interactive and not getattr(widget, "_dse_help", False):
                DSEToolTip(widget, lambda w=widget: self._help_text_for_widget(w))
                widget._dse_help = True
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._install_context_help_recursive(child)
        except Exception:
            pass

    def _configure_treeview_for_dpi(self):
        """Prevent glyphs and numbers being clipped on scaled Windows displays."""
        try:
            import tkinter.font as tkfont
            font = tkfont.nametofont("TkDefaultFont")
            linespace = int(font.metrics("linespace"))
            style = ttk.Style(self.root)
            style.configure("Treeview", rowheight=max(26, linespace + 10), font=font)
            style.configure("Treeview.Heading", font=font)
        except Exception:
            pass
