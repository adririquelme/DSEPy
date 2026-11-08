# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk


class DSEProgressDialog:
    """Modal progress dialog for real-time tracking with cancellation support."""
    def __init__(self, parent, title=None, translator=None):
        self._tr = translator or getattr(parent, "tr", lambda key, **values: key)
        if title is None:
            title = self._tr("progress.dialog_title")
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry("440x190")
        self.top.resizable(False, False)
        self.top.attributes("-topmost", True)
        self.top.grab_set()

        self.cancelled = False

        self.lbl_title = tk.Label(self.top, text=self._tr("progress.processing_spatial_clustering"), font=("Helvetica", 10, "bold"))
        self.lbl_title.pack(pady=(12, 4))

        self.lbl_status = tk.Label(self.top, text=self._tr("progress.initializing"), font=("Helvetica", 9), wraplength=400)
        self.lbl_status.pack(pady=(0, 8))

        self.pbar = ttk.Progressbar(self.top, orient="horizontal", length=370, mode="determinate")
        self.pbar.pack(pady=4)

        self.btn_cancel = tk.Button(
            self.top, text=self._tr("progress.cancel_process"), command=self.cancel,
            bg="#f8d7da", fg="#721c24", font=("Helvetica", 9, "bold"), width=15
        )
        self.btn_cancel.pack(pady=(8, 0))

        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        self.top.update()

    def cancel(self):
        self.cancelled = True
        self.lbl_status.config(text=self._tr("progress.cancelling"))
        self.btn_cancel.config(state=tk.DISABLED)

    def update_progress(self, percent, status_text):
        if self.cancelled:
            return False
        self.pbar["value"] = percent
        self.lbl_status.config(text=status_text)
        self.top.update()
        return not self.cancelled

    def close(self):
        try:
            self.top.grab_release()
            self.top.destroy()
        except Exception:
            pass
