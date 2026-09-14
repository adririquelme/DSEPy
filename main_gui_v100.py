# -*- coding: utf-8 -*-

import sys
import os
import importlib
import time
import json
import base64
import webbrowser

from datetime import datetime

# Single source of truth for the DSEPy version. Change this value only when releasing a new version.
DSE_VERSION = "1.0.0"


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


def _fit_window_to_screen(window, preferred_width=1160, preferred_height=760):
    """Choose a compact initial size without exceeding the work area."""
    window.update_idletasks()
    screen_w = max(640, window.winfo_screenwidth())
    screen_h = max(480, window.winfo_screenheight())
    width = min(preferred_width, max(640, int(screen_w * 0.90)))
    height = min(preferred_height, max(480, int(screen_h * 0.85)))
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    window.geometry("{}x{}+{}+{}".format(width, height, x, y))
    window.minsize(min(900, width), min(600, height))

# 1. Resolve the plugin directory without assuming that __file__ exists.
# 1. Resolve the plugin directory in CloudCompare exec mode.
def _resolve_plugins_dir():
    candidates = []

    script_file = globals().get("__file__")
    if script_file:
        candidates.append(
            os.path.dirname(os.path.abspath(script_file))
        )

    system_drive = os.environ.get("SystemDrive", "")
    if system_drive:
        candidates.append(
            os.path.join(system_drive + os.sep, "CCPlugins")
        )

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(
            os.path.join(appdata, "CCPlugins")
        )

    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        candidates.append(
            os.path.join(localappdata, "CCPlugins")
        )

    candidates.append(os.getcwd())

    candidates.extend(
        path
        for path in sys.path
        if isinstance(path, str) and path
    )

    checked = []
    seen = set()

    for folder in candidates:
        folder = os.path.abspath(folder)
        key = os.path.normcase(folder)

        if key in seen:
            continue

        seen.add(key)
        checked.append(folder)

        if not os.path.isdir(folder):
            continue

        stereonet_path = os.path.join(
            folder,
            "stereonet.py"
        )

        if os.path.isfile(stereonet_path):
            return folder

        # CloudCompare may execute this script without __file__.
        # Also check one level below known plugin roots (e.g. CCPlugins\DSEpy).
        try:
            children = os.listdir(folder)
        except OSError:
            children = []

        for name in children:
            child = os.path.join(folder, name)
            if os.path.isdir(child) and os.path.isfile(
                os.path.join(child, "stereonet.py")
            ):
                return child

    raise RuntimeError(
        "DSE plugin directory not found. Checked: "
        + " | ".join(checked)
    )


plugins_dir = _resolve_plugins_dir()

if plugins_dir in sys.path:
    sys.path.remove(plugins_dir)

sys.path.insert(0, plugins_dir)

from i18n import I18nManager

# 2. Add the user site-packages that matches the embedded Python runtime.
def _add_runtime_packages():
    major = sys.version_info.major
    minor = sys.version_info.minor
    version_dir = "Python{}{}".format(major, minor)
    roots = []
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        roots.append(os.path.join(appdata, "Python", version_dir, "site-packages"))
    if localappdata:
        roots.append(os.path.join(
            localappdata, "Programs", "Python", version_dir, "Lib", "site-packages"
        ))

    existing = []
    for folder in roots:
        if os.path.isdir(folder) and folder not in existing:
            existing.append(folder)

    # Put external binary packages after the plugin directory but before other paths.
    for folder in reversed(existing):
        if folder in sys.path:
            sys.path.remove(folder)
        sys.path.insert(1, folder)

    # Python 3.8+ restricts Windows DLL lookup. Explicitly register wheel DLL folders.
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        dll_folders = []
        for folder in existing:
            dll_folders.extend([
                folder,
                os.path.join(folder, "numpy.libs"),
                os.path.join(folder, "scipy.libs"),
            ])
        handles = []
        for folder in dll_folders:
            if os.path.isdir(folder):
                try:
                    handles.append(os.add_dll_directory(folder))
                except OSError:
                    pass
        return handles
    return []

_dse_dll_handles = _add_runtime_packages()

try:
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as path_effects
except Exception as exc:
    details = (
        "DSE dependency import failed. "
        "Embedded Python: {}.{}.{}; executable: {}; error: {}: {}"
    ).format(
        sys.version_info.major, sys.version_info.minor, sys.version_info.micro,
        sys.executable, type(exc).__name__, exc
    )
    raise RuntimeError(details) from exc

# colorcet is optional. If present, importing it registers all "cet_*"
# colormap names (e.g. "cet_rainbow4") with matplotlib as a side effect.
# If it is missing, the plugin still works fine with the standard
# matplotlib colormaps; _cluster_rgb() falls back gracefully.
try:
    import colorcet  # noqa: F401
    _COLORCET_AVAILABLE = True
except Exception:
    _COLORCET_AVAILABLE = False

import pycc
import tkinter as tk
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None
from tkinter import messagebox, ttk, scrolledtext, filedialog

import stereonet
import colour_optimisation as colour_opt
importlib.reload(stereonet)
importlib.reload(colour_opt)


class DSEProgressDialog:
    """Modal progress dialog for real-time tracking with cancellation support."""
    def __init__(self, parent, title=None):
        self._tr = getattr(parent, "tr", lambda key, **values: key)
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


class DSEMainApp:
    def __init__(self, root):
        self.root = root
        # Persistent execution log: keep the same messages shown in the GUI,
        # including their current language, for post-run/i18n verification.
        self._log_file_path = os.path.join(plugins_dir, "DSE_execution_log.txt")
        self.root.title(f"DSE - Discontinuity Set Extractor {DSE_VERSION}")
        _fit_window_to_screen(self.root)
        self.i18n = I18nManager(plugins_dir, default_language="en")
        stereonet.set_translator(self.tr)
        colour_opt.set_translator(self.tr)
        self.language = self.i18n.language
        self.facet_colormap = "turbo"
        self.saved_method = self._load_method_settings()

        self.cached_X = None
        self.cached_Y = None
        self.cached_Z = None
        self.cached_xp = None
        self.cached_yp = None
        self.cached_projection = None
        self.cached_density_grids = {}
        self.principal_poles = []
        self.display_principal_poles = []
        self.cached_pole_space = "original"
        self.optimised_colour_rotation = None
        self.optimised_colour_angles = None
        self.optimised_colour_objective = None
        self.optimised_colour_objective_name = None
        self.optimised_colour_evaluations = None
        self.optimised_colour_iterations = None
        self.optimised_colour_seconds = None
        self.pole_space_var = None
        self.cluster_planes_results = None
        self.cluster_fisher_results = []
        self.poles_revision = 0
        self.js_revision = -1
        self.poles_review_status = "empty"

        self.fig = None
        self.ax = None
        self.cbar = None
        self.family_fig = None
        self.family_ax = None
        self.family_plot_data = None

        self._build_menu()
        # Icons must be loaded before _build_ui because the Step 1 action
        # buttons are created there and _make_icon_button_v030 accesses
        # self.icons during construction.
        self._load_icons_v030()
        self._build_ui()
        self._configure_treeview_for_dpi()
        self._apply_saved_settings()
        self._refresh_action_labels()
        self._rebuild_icon_action_rows_v030()
        self._apply_icons_v030()
        self._install_tooltips()
        self._install_context_help_recursive(self.root)
        self.set_language(self.language)
        self.root.option_add("*Font", ("Segoe UI", 9))
        self.root.option_add("*Button.Font", ("Segoe UI", 9))
        self.root.option_add("*Entry.Font", ("Segoe UI", 9))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Startup banner and scientific references. The version is controlled
        # only by DSE_VERSION at the top of this module.
        self.log(self.tr("log.greetings", version=DSE_VERSION))
        self.log(self.tr("log.startup_version", version=DSE_VERSION))
        self.log(self.tr("log.startup_ref_dse"))
        self.log(self.tr("log.startup_ref_spacing"))
        self.log(self.tr("log.startup_ref_persistence"))
        self.log(self.tr("log.startup_ref_colour"))
        self.log(self.tr("log.startup_wiki"))
        
        # CloudCompare may finish synchronising the current selection just
        # after the plugin window is created.  Re-check once the event loop is
        # idle and again shortly afterwards so Step 1 becomes available
        # without requiring the user to click its tab.
        self.check_cloud_and_update_workflow()
        self.root.after_idle(self._initial_workflow_check)
        self.root.after(350, self._initial_workflow_check)

    def _catalog(self):
        return self.i18n.catalogs

    def tr(self, key, **values):
        template=self.i18n.get(key,default=key)
        try: return template.format(**values)
        except (KeyError,IndexError,ValueError): return template

    def tx(self, text):
        return self.i18n.get(text,default=text)

    def _settings_path(self):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or ""
        folder = os.path.join(base, "DSE")
        return folder, os.path.join(folder, "settings.json")

    def _load_method_settings(self):
        defaults = {
            "language": "en", "facet_colormap": "turbo",
            "projection": "Equal-angle", "bins": 6, "min_angle": 30,
            "max_poles": 5, "density_style": "Contour Lines",
            "labels": 1, "js_cone": 30.0, "k_neighbor": 4,
            "k_sigma": 2.0, "dbscan_minpts": 4,
            "minimum_cluster_size": 100, "merge_sigma": 1.5,
            "fix_orientation": 1, "sort_index": 0,
            "random_seed": "", "create_clouds": 1,
            "export_family_clouds": 1,
        }
        _, path = self._settings_path()
        try:
            with open(path, "r", encoding="ascii") as stream:
                defaults.update(json.load(stream))
        except Exception:
            pass
        self.language = self.i18n.set_language(defaults["language"])
        self.facet_colormap = defaults["facet_colormap"]
        try:
            plt.get_cmap(self.facet_colormap)
        except (ValueError, KeyError):
            self.facet_colormap = "turbo"
        return defaults

    def _save_method_settings(self):
        data = {
            "language": self.language, "facet_colormap": self.facet_colormap,
            "projection": self._canonical_projection(), "bins": int(self.spin_bins.get()),
            "min_angle": float(self.spin_angle.get()), "max_poles": int(self.spin_maxpoles.get()),
            "density_style": self._canonical_density_style(), "labels": int(self.labeled_var.get()),
            "js_cone": float(self.spin_js_cone.get()), "k_neighbor": int(self.spin_k_neighbor.get()),
            "k_sigma": float(self.spin_k_sigma.get()), "dbscan_minpts": int(self.spin_dbscan_minpts.get()),
            "minimum_cluster_size": int(self.spin_min_cluster_size.get()),
            "merge_sigma": float(self.spin_merge_sigma.get()),
            "fix_orientation": int(self.fix_orientation_var.get()),
            "sort_index": int(self.sort_combo.current()), "random_seed": self.ent_random_seed.get().strip(),
            "create_clouds": int(self.create_cluster_clouds_var.get()),
            "export_family_clouds": int(self.export_family_clouds_var.get()),
        }
        folder, path = self._settings_path()
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="ascii") as stream:
            json.dump(data, stream, indent=2)

    @staticmethod
    def _set_control(control, value):
        try:
            control.delete(0, tk.END)
            control.insert(0, str(value))
        except Exception:
            pass

    def _apply_saved_settings(self):
        s = self.saved_method
        try: self.proj_combo.set({"Equal-angle": self.tx("projection.equal_angle"), "Equal-area": self.tx("projection.equal_area"), "Equal-proportion": self.tx("projection.equal_proportion")}.get(s["projection"], s["projection"]))
        except Exception: pass
        self._set_control(self.spin_bins, s["bins"])
        self._set_control(self.spin_angle, s["min_angle"])
        self._set_control(self.spin_maxpoles, s["max_poles"])
        try: self.style_combo.set({"Contour Lines": self.tx("gui.contour_lines"), "Filled Contours": self.tx("gui.filled_contours")}.get(s["density_style"], s["density_style"]))
        except Exception: pass
        self.labeled_var.set(s["labels"])
        self._set_control(self.spin_js_cone, s["js_cone"])
        self._set_control(self.spin_k_neighbor, s["k_neighbor"])
        self._set_control(self.spin_k_sigma, s["k_sigma"])
        self._set_control(self.spin_dbscan_minpts, s["dbscan_minpts"])
        self._set_control(self.spin_min_cluster_size, s["minimum_cluster_size"])
        self._set_control(self.spin_merge_sigma, s["merge_sigma"])
        self.fix_orientation_var.set(s["fix_orientation"])
        self.sort_combo.current(min(max(int(s["sort_index"]), 0), 2))
        self._set_control(self.ent_random_seed, s["random_seed"])
        self.create_cluster_clouds_var.set(s["create_clouds"])
        self.export_family_clouds_var.set(s.get("export_family_clouds", 1))

    def add_tooltip(self, widget, key):
        DSEToolTip(widget, lambda: self.tr(key))
        try:
            widget._dse_help = True
            widget._dse_tooltip_key = key
        except Exception:
            pass

    def _icons_directory(self):
        return os.path.join(plugins_dir, "icons")

    def _load_resized_icon(self, path, box_size=28, canvas_size=32):
        """Load any PNG size into a centered transparent GUI icon.

        The original aspect ratio is preserved. The image is never stretched
        or cropped. A transparent canvas gives all controls a uniform size.
        """
        if Image is None or ImageTk is None:
            # Safe fallback when Pillow is unavailable. The original image is
            # loaded without resizing, so the program remains functional.
            return tk.PhotoImage(file=path)

        image = Image.open(path).convert("RGBA")
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid icon size: {path}")

        scale = min(float(box_size) / width, float(box_size) / height)
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        image = image.resize(
            (resized_width, resized_height),
            Image.Resampling.LANCZOS
        )

        canvas = Image.new(
            "RGBA", (int(canvas_size), int(canvas_size)), (0, 0, 0, 0)
        )
        x = (canvas_size - resized_width) // 2
        y = (canvas_size - resized_height) // 2
        canvas.alpha_composite(image, (x, y))
        return ImageTk.PhotoImage(canvas, master=self.root)

    def _load_icons(self):
        """Load and normalize user-provided icons from the DSE icons folder."""
        self.icons = {}
        names = (
            "plot_poles", "principal_poles", "classify", "plot_families",
            "cluster_analysis", "cluster_facets", "refresh", "settings",
            "info", "add", "apply", "delete", "move_up", "move_down",
            "open_folder", "save", "spacing", "persistence", "imagen_rotacion"
        )
        directory = self._icons_directory()
        for name in names:
            path = os.path.join(directory, name + ".png")
            if not os.path.isfile(path):
                continue
            try:
                # Compact and main buttons share a 32 px transparent canvas.
                # Actual artwork is fitted inside 27 px to leave breathing room.
                self.icons[name] = self._load_resized_icon(
                    path, box_size=27, canvas_size=32
                )
            except Exception as exc:
                self.log(self.tr("log.icon_warning", name=name, exc=exc))

    def _apply_icons(self):
        """Apply uniform icon geometry without cropping button content."""
        primary = (
            (self.btn_poles, "plot_poles"),
            (self.btn_density, "principal_poles"),
            (self.btn_classify_js, "classify"),
            (self.btn_poles_by_family, "plot_families"),
            (self.btn_clusterize, "cluster_analysis"),
            (self.btn_facets, "cluster_facets"),
        )
        for button, name in primary:
            icon = self.icons.get(name)
            if icon is not None:
                button.configure(
                    image=icon, compound=tk.LEFT, anchor=tk.W,
                    padx=10, pady=5, height=34
                )

        compact = (
            (self.btn_addp, "add"),
            (self.btn_apply_edit, "apply"),
            (self.btn_delp, "delete"),
            (self.btn_mup, "move_up"),
            (self.btn_mdown, "move_down"),
        )
        fallback = {
            "add": "+", "apply": "OK", "delete": "X",
            "move_up": "Up", "move_down": "Down"
        }
        for button, name in compact:
            icon = self.icons.get(name)
            if icon is not None:
                button.configure(
                    image=icon, text="", compound=tk.CENTER,
                    width=38, height=36, padx=3, pady=3
                )
            else:
                button.configure(text=fallback[name], width=6, height=2)

        # Tk menus support PNG images as well.
        tools_icons = {
            0: "imagen_rotacion",
            2: "spacing",
            3: "persistence",
        }
        for index, name in tools_icons.items():
            icon = self.icons.get(name)
            if icon is not None:
                try:
                    self.tools_menu.entryconfig(index, image=icon, compound=tk.LEFT)
                except Exception:
                    pass

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

    def _icons_directory_v030(self):
        return os.path.join(plugins_dir, "icons")

    def _load_resized_icon_v030(self, path, box_size=40, canvas_size=46):
        """Fit any PNG proportionally and center its non-transparent artwork."""
        if Image is None or ImageTk is None:
            return tk.PhotoImage(file=path)
        image = Image.open(path).convert("RGBA")
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid icon: {path}")
        scale = min(float(box_size) / width, float(box_size) / height)
        width = max(1, int(round(width * scale)))
        height = max(1, int(round(height * scale)))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        canvas.alpha_composite(
            image, ((canvas_size - width) // 2, (canvas_size - height) // 2)
        )
        return ImageTk.PhotoImage(canvas, master=self.root)

    def _load_icons_v030(self):
        self.icons = {}
        names = (
            "plot_poles", "principal_poles", "classify", "plot_families",
            "cluster_analysis", "cluster_facets", "display_density", "refresh",
            "add", "apply", "delete", "move_up", "move_down",
            "spacing", "persistence", "imagen_rotacion", "imagen_HSV_icono"
        )
        for name in names:
            path = os.path.join(self._icons_directory_v030(), name + ".png")
            if not os.path.isfile(path):
                continue
            try:
                self.icons[name] = self._load_resized_icon_v030(
                    path, box_size=36, canvas_size=42
                )
            except Exception as exc:
                try:
                    self.log(self.tr("log.icon_warning", name=name, exc=exc))
                except Exception:
                    pass

    def _make_icon_button_v030(self, parent, icon_name, command, tooltip_key, fallback):
        button_width = 58
        button_height = 54
        button = tk.Button(
            parent, command=command, width=button_width, height=button_height,
            padx=3, pady=3, relief=tk.RAISED
        )
        icon = self.icons.get(icon_name)
        if icon is None:
            if not hasattr(self, "_blank_action_icon_v030"):
                self._blank_action_icon_v030 = tk.PhotoImage(
                    master=self.root, width=46, height=46
                )
            icon = self._blank_action_icon_v030
            button.configure(
                image=icon, text=fallback, compound=tk.CENTER,
                font=("Helvetica", 7, "bold")
            )
        else:
            button.configure(image=icon, text="", compound=tk.CENTER)
        button._dse_icon_image = icon
        try:
            self.add_tooltip(button, tooltip_key)
        except Exception:
            pass
        return button

    def _rebuild_icon_action_rows_v030(self):
        """Create the requested icon-only action layout."""
        # Hide original action controls while preserving all calculation methods.
        for name in (
            "btn_poles", "btn_density", "btn_show_density", "btn_classify_js",
            "btn_poles_by_family", "btn_clusterize", "btn_facets"
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.pack_forget()
                except Exception:
                    try:
                        widget.grid_remove()
                    except Exception:
                        pass

        # Step 1 actions: plot poles, calculate density and show cached density.
        self.v030_block1 = tk.Frame(self.grp_step1)
        self.v030_block1.pack(fill=tk.X, padx=5, pady=(8, 6))
        self.btn_poles = self._make_icon_button_v030(
            self.v030_block1, "plot_poles", self.run_plot_poles,
            "tip.plot_poles", "Poles"
        )
        self.btn_density = self._make_icon_button_v030(
            self.v030_block1, "principal_poles", self.run_plot_density,
            "tip.density_action", "Calculate"
        )
        self.btn_show_density = self._make_icon_button_v030(
            self.v030_block1, "display_density", self.run_show_density,
            "tip.show_density", "Show density"
        )
        for button in (
                self.btn_poles, self.btn_density, self.btn_show_density):
            button.pack(side=tk.LEFT, padx=6, pady=2)

        # Step 2 actions: assign principal poles, then plot classified normals.
        self.v030_block2 = tk.Frame(self.grp_step2)
        self.v030_block2.pack(fill=tk.X, padx=5, pady=(8, 6))
        self.btn_classify_js = self._make_icon_button_v030(
            self.v030_block2, "classify", self.run_classify_js,
            "tip.classify_action", "Assign DS"
        )
        self.btn_poles_by_family = self._make_icon_button_v030(
            self.v030_block2, "plot_families", self.run_plot_poles_by_family,
            "tip.family_plot_action", "Plot normals"
        )
        for button in (self.btn_classify_js, self.btn_poles_by_family):
            button.pack(side=tk.LEFT, padx=6, pady=2)
        self.btn_poles_by_family.config(state=tk.DISABLED)

        # Step 3 actions: cluster analysis and patch/facet export.
        self.v030_block3 = tk.Frame(self.grp_step3)
        self.v030_block3.pack(fill=tk.X, padx=5, pady=(8, 6))
        self.btn_clusterize = self._make_icon_button_v030(
            self.v030_block3, "cluster_analysis", self.run_clusterize,
            "tip.cluster", "Clusters"
        )
        self.btn_facets = self._make_icon_button_v030(
            self.v030_block3, "cluster_facets", self.create_cluster_facets,
            "tip.facets", "Facets"
        )
        for button in (self.btn_clusterize, self.btn_facets):
            button.configure(width=58, height=54, padx=3, pady=3)
            button.pack(side=tk.LEFT, padx=6, pady=2)
        self.btn_facets.config(state=tk.DISABLED)

    def _apply_icons_v030(self):
        """Apply workflow and utility icons with consistent visual geometry."""
        refresh_path = os.path.join(
            self._icons_directory_v030(), "refresh.png"
        )
        refresh_icon = None
        if os.path.isfile(refresh_path):
            try:
                refresh_icon = self._load_resized_icon_v030(
                    refresh_path, box_size=46, canvas_size=50
                )
            except Exception as exc:
                self.log(f"Icon load warning (refresh): {exc}")
        if refresh_icon is None:
            refresh_icon = self.icons.get("refresh")
        if refresh_icon is not None:
            self.btn_refresh_cloud.configure(
                image=refresh_icon, text="", compound=tk.CENTER,
                width=58, height=54, padx=3, pady=3
            )
            self.btn_refresh_cloud._dse_icon_image = refresh_icon
        else:
            self.btn_refresh_cloud.configure(
                text=self.tr("Refresh"), width=58, height=54,
                padx=3, pady=3, font=("Segoe UI", 8, "bold")
            )


        for button, name, fallback in (
            (self.btn_addp, "add", "+"),
            (self.btn_apply_edit, "apply", "OK"),
            (self.btn_delp, "delete", "X"),
            (self.btn_mup, "move_up", "Up"),
            (self.btn_mdown, "move_down", "Down"),
        ):
            icon = self.icons.get(name)
            if icon is not None:
                button.configure(
                    image=icon, text="", compound=tk.CENTER,
                    width=46, height=44, padx=2, pady=2
                )
                button._dse_icon_image = icon
            else:
                button.configure(text=fallback, width=6, height=2)
        tools_icons = {
            0: "imagen_rotacion",
            2: "spacing",
            3: "persistence",
        }
        for index, name in tools_icons.items():
            icon = self.icons.get(name)
            if icon is not None:
                try:
                    self.tools_menu.entryconfig(index, image=icon, compound=tk.LEFT)
                except Exception:
                    pass
        # New controls must inherit the current workflow state.
        try:
            self.check_cloud_and_update_workflow()
        except Exception:
            pass

    def _refresh_action_labels(self):
        """Apply compact icons and localized descriptive button text."""
        labels = {
            "poles": self.tr("action.poles", default="◎  Plot Poles"),
            "density": self.tr("action.density", default="⚙  Density and Principal Poles"),
            "classify": self.tr("action.classify", default="✓  Classify Point Cloud (JS)"),
            "families": self.tr("action.families", default="◉  Poles by Family (JS)"),
            "cluster": self.tr("action.cluster", default="▦  Run Cluster Analysis"),
            "facets": self.tr("action.facets", default="△  Create Cluster Facets"),
            "add": self.tr("action.add", default="+  Add Pole"),
            "apply": self.tr("action.apply", default="✓  Apply Changes"),
            "delete": self.tr("action.delete", default="-  Delete Pole"),
            "up": self.tr("action.up", default="↑  Move Up"),
            "down": self.tr("action.down", default="↓  Move Down"),
        }
        self.btn_poles.config(text=labels["poles"])
        self.btn_density.config(text=labels["density"])
        self.btn_classify_js.config(text=labels["classify"])
        self.btn_poles_by_family.config(text=labels["families"])
        self.btn_clusterize.config(text=labels["cluster"])
        self.btn_facets.config(text=labels["facets"])
        # Compact pole-edit controls remain icon-only. Their localized
        # explanations are provided by tooltips.
        # Image-backed controls must remain icon-only in every language.
        if getattr(self, "icons", None):
            for button in (
                self.btn_poles, self.btn_density, self.btn_show_density,
                self.btn_classify_js, self.btn_poles_by_family,
                self.btn_clusterize, self.btn_facets, self.btn_addp,
                self.btn_apply_edit, self.btn_delp, self.btn_mup, self.btn_mdown
            ):
                try:
                    if str(button.cget("image")):
                        button.configure(text="", compound=tk.CENTER, anchor=tk.CENTER)
                except Exception:
                    pass
        if not getattr(self, "icons", None):
            self.btn_addp.config(text=labels["add"])
            self.btn_apply_edit.config(text=labels["apply"])
            self.btn_delp.config(text=labels["delete"])
            self.btn_mup.config(text=labels["up"])
            self.btn_mdown.config(text=labels["down"])

def set_language(self, language, restart_required=False):
    """Set the interface language. A restart is required after changing it."""
    requested = language
    self.i18n.reload()
    self.language = self.i18n.set_language(requested)

    if restart_required:
        self._save_method_settings()

if restart_required:
    import tkinter as tk

    language_name = self.i18n.metadata.get(
        self.language, {}
    ).get("native_name", self.language)

    dialog = tk.Toplevel(self.root)
    dialog.title(self.tr("language.changed", language=language_name))
    dialog.transient(self.root)
    dialog.grab_set()
    dialog.resizable(False, False)

    message = (
        f"The language has been changed to {language_name}.\n\n"
        "Please restart DSEPy to apply the new language "
        "to all menus, options and interface elements."
    )

    tk.Label(
        dialog,
        text=message,
        justify="left",
        padx=20,
        pady=20,
    ).pack()

    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=(0, 15))

    def continue_without_restart():
        dialog.destroy()

        self._translate_widget_tree(self.root)
        self._refresh_language_dependent_controls()
        self._refresh_action_labels()
        self._refresh_menu_language()
        self._refresh_table_language()
        self._set_poles_status(self.poles_review_status)

    def close_and_restart():
        dialog.destroy()
        self.root.destroy()

    tk.Button(
        button_frame,
        text="Continue",
        command=continue_without_restart,
        width=16,
    ).pack(side="left", padx=5)

    tk.Button(
        button_frame,
        text="Close and restart",
        command=close_and_restart,
        width=16,
    ).pack(side="left", padx=5)

    dialog.protocol(
        "WM_DELETE_WINDOW",
        continue_without_restart
    )

    self.root.wait_window(dialog)

    return self.language

    self._translate_widget_tree(self.root)
    self._refresh_language_dependent_controls()
    self._refresh_action_labels()
    self._refresh_menu_language()
    self._refresh_table_language()
    self._set_poles_status(self.poles_review_status)

    self.log(
        self.tr(
            "language.changed",
            language=self.i18n.metadata.get(
                self.language, {}
            ).get("native_name", self.language)
        )
    )

    if self.fig is not None and self.ax is not None:
        self.ax.set_title(
            self.tr(
                "plot.density_title",
                projection=self.cached_projection or ""
            )
        )
        self.fig.canvas.draw_idle()

    return self.language

    def _canonical_projection(self):
        value = self.proj_combo.get()
        labels = {
            self.tx("projection.equal_angle"): "Equal-angle",
            self.tx("projection.equal_area"): "Equal-area",
            self.tx("projection.equal_proportion"): "Equal-proportion",
        }
        return labels.get(value, value)

    def _canonical_density_style(self):
        value = self.style_combo.get()
        labels = {
            self.tx("gui.contour_lines"): "Contour Lines",
            self.tx("gui.filled_contours"): "Filled Contours",
        }
        return labels.get(value, value)

    def _canonical_pole_space(self):
        value = self.pole_space_var.get() if hasattr(self, "pole_space_var") else "original"
        return {
            self.tx("poles.source.original"): "original",
            self.tx("poles.source.rotated"): "rotated",
            "original": "original",
            "rotated": "rotated",
        }.get(value, value)

    def _canonical_facet_type(self):
        value = self.facet_type_var.get() if hasattr(self, "facet_type_var") else "convex"
        return {
            self.tx("facet.type.convex"): "convex",
            self.tx("facet.type.disk"): "disk",
            self.tx("facet.type.ellipse"): "ellipse",
            self.tx("facet.type.rectangle"): "rectangle",
            "convex": "convex", "disk": "disk", "ellipse": "ellipse", "rectangle": "rectangle",
        }.get(value, value)

    def _refresh_language_dependent_controls(self):
        if hasattr(self, "log_frame"):
            self.log_frame.configure(text=" " + self.tr("gui.execution_log") + " ")
        if hasattr(self, "pole_space_combo"):
            current_space = self._canonical_pole_space()
            self.pole_space_combo.configure(values=(
                self.tx("poles.source.original"), self.tx("poles.source.rotated")
            ))
            self.pole_space_combo.set({
                "original": self.tx("poles.source.original"),
                "rotated": self.tx("poles.source.rotated"),
            }.get(current_space, current_space))
        if hasattr(self, "proj_combo"):
            current_projection = self._canonical_projection()
            projection_values = (self.tx("projection.equal_angle"), self.tx("projection.equal_area"), self.tx("projection.equal_proportion"))
            self.proj_combo.configure(values=projection_values)
            self.proj_combo.set({
                "Equal-angle": self.tx("projection.equal_angle"),
                "Equal-area": self.tx("projection.equal_area"),
                "Equal-proportion": self.tx("projection.equal_proportion"),
            }.get(current_projection, current_projection))
        if hasattr(self, "style_combo"):
            current_style = self._canonical_density_style()
            style_values = (self.tx("gui.contour_lines"), self.tx("gui.filled_contours"))
            self.style_combo.configure(values=style_values)
            self.style_combo.set({
                "Contour Lines": self.tx("gui.contour_lines"),
                "Filled Contours": self.tx("gui.filled_contours"),
            }.get(current_style, current_style))
        if hasattr(self, "self.poles_frame"):
            self.poles_frame.configure(text=" " + self.tx("gui.principal_pole_analysis") + " ")
        if hasattr(self, "grp_step1"):
            self.grp_step1.configure(text=" " + self.tx("gui.principal_poles") + " ")
        if hasattr(self, "grp_step2"):
            self.grp_step2.configure(text=" " + self.tx("gui.step2") + " ")
        if hasattr(self, "grp_step3"):
            self.grp_step3.configure(text=self.tx("Spatial clustering and plane fitting"))
        if hasattr(self, "self.cluster_parameters"):
            self.cluster_parameters.configure(text=" " + self.tx("Cluster analysis") + " ")
        if hasattr(self, "self.plane_parameters"):
            self.plane_parameters.configure(text=" " + self.tx("Plane calculation") + " ")
        if hasattr(self, "self.facet_export"):
            self.facet_export.configure(text=" " + self.tx("Facet export") + " ")
        if hasattr(self, "facet_type_combo"):
            current_facet = self._canonical_facet_type()
            facet_values = (self.tx("facet.type.convex"), self.tx("facet.type.disk"), self.tx("facet.type.ellipse"), self.tx("facet.type.rectangle"))
            self.facet_type_combo.configure(values=facet_values)
            self.facet_type_combo.set({
                "convex": self.tx("facet.type.convex"), "disk": self.tx("facet.type.disk"),
                "ellipse": self.tx("facet.type.ellipse"), "rectangle": self.tx("facet.type.rectangle"),
            }.get(current_facet, current_facet))

        if hasattr(self, "workflow_notebook"):
            labels=(self.tx("1. Principal poles"),self.tx("2. DS classification"),self.tx("3. Spatial clustering"))
            for tab, label in zip(
                    (self.step1_tab, self.step2_tab, self.step3_tab), labels):
                self.workflow_notebook.tab(tab, text=label)
        current = self.sort_combo.current() if hasattr(self, "sort_combo") else 0
        if hasattr(self, "sort_combo"):
            self.sort_combo.configure(values=[
                self.tr("sort.size"), self.tr("sort.d"), self.tr("sort.random")
            ])
            self.sort_combo.current(max(0, current))

    def _translate_widget_tree(self, widget):
        try:
            source=getattr(widget,"_i18n_source_text",None) or self.i18n.source_for(widget.cget("text"))
            widget._i18n_source_text=source; widget.configure(text=self.tx(source))
        except Exception: pass
        for child in widget.winfo_children(): self._translate_widget_tree(child)
        try:
            if isinstance(widget,ttk.Notebook):
                for tab_id in widget.tabs():
                    source=self.i18n.source_for(widget.tab(tab_id,"text")); widget.tab(tab_id,text=self.tx(source))
        except Exception: pass
        self.root.title(f"DSE - Discontinuity Set Extractor {DSE_VERSION}")

    def _refresh_table_language(self):
        """Translate headings and keep numeric columns readable under DPI scaling."""
        pole_headers = {
            "ID": "table.id", "DipDir": "table.dip_direction",
            "Dip": "table.dip", "Density": "table.density",
            "FisherK": "table.fisher_k", "N": "table.sample_count",
        }
        plane_headers = {
            "Family": "table.family", "Cl": "table.cluster",
            "DipDir": "table.dip_direction", "Dip": "table.dip",
            "A": "table.a", "B": "table.b", "C": "table.c",
            "D": "table.d", "Size": "table.point_count",
        }
        fisher_headers = {
            "Family": "DS", "DipDir": "table.dip_direction",
            "Dip": "table.dip", "N": "Clusters",
            "K": "table.fisher_k", "MaxDev": "Max deviation (deg)",
            "Confidence": "Confidence (deg)",
        }
        if hasattr(self, "tree"):
            for column, key in pole_headers.items():
                self.tree.heading(column, text=self.tr(key))
        if hasattr(self, "planes_tree"):
            for column, key in plane_headers.items():
                self.planes_tree.heading(column, text=self.tr(key))
        if hasattr(self, "cluster_fisher_tree"):
            for column, key in fisher_headers.items():
                self.cluster_fisher_tree.heading(column, text=self.tx(key))

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

    def _install_tooltips(self):
        controls = [
            (self.btn_refresh_cloud, "tip.refresh"),
            (self.proj_combo, "tip.projection"), (self.spin_bins, "tip.bins"),
            (self.spin_angle, "tip.angle"), (self.spin_maxpoles, "tip.maxpoles"),
            (self.style_combo, "tip.style"), (self.chk_labels, "tip.labels"),
            (self.btn_show_density, "tip.show_density"),
            (self.spin_js_cone, "tip.jscone"), (self.spin_k_neighbor, "tip.kneighbor"),
            (self.spin_k_sigma, "tip.ksigma"), (self.spin_dbscan_minpts, "tip.dbscanminpts"),
            (self.spin_min_cluster_size, "tip.minclustersize"),
            (self.spin_merge_sigma, "tip.merge"), (self.sort_combo, "tip.sort"),
            (self.ent_random_seed, "tip.seed"), (self.btn_clusterize, "tip.cluster"),
            (self.chk_export_family_clouds, "tip.family_clouds"),
            (self.btn_facets, "tip.facets"),
            (self.tree, "tip.pole_table"),
            (self.btn_addp, "tip.pole_add"),
            (self.btn_apply_edit, "tip.pole_apply"),
            (self.btn_delp, "tip.pole_delete"),
            (self.btn_mup, "tip.pole_up"),
            (self.btn_mdown, "tip.pole_down"),
        ]
        for widget, key in controls:
            self.add_tooltip(widget, key)

    def _on_close(self):
        try: self._save_method_settings()
        except Exception: pass
        self.root.destroy()

    def _localize_log_message(self, message):
        """Localize every message before it reaches the visible log."""
        return self.tx(str(message))

    def log(self, message):
        """Log to both the GUI console and a persistent text file."""
        timestamp = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        localized_message = self._localize_log_message(message)
        line = f"[{timestamp}] [{self.language}] {localized_message}"
        try:
            self.txt_log.config(state=tk.NORMAL)
            self.txt_log.insert(tk.END, line + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.config(state=tk.DISABLED)
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(self._log_file_path), exist_ok=True)
            with open(self._log_file_path, "a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
        except Exception:
            # Logging must never interfere with the DSE workflow.
            pass

    def _initial_workflow_check(self):
        """Re-check CloudCompare selection after its UI has synchronised."""
        try:
            self.check_cloud_and_update_workflow()
        except Exception as exc:
            try:
                self.log(self.tr("log.workflow_check_warning", exc=exc))
            except Exception:
                pass

    def show_settings(self):
        try:
            self.i18n.reload()
        except Exception as exc:
            self.log(
                "Warning: could not reload i18n catalogs: "
                "{}: {}".format(type(exc).__name__, exc)
            )
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tx("Settings"))
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Button bar pinned to the bottom of the window FIRST, so it is
        # always visible regardless of how tall the content above ends
        # up being (and regardless of manual resizing).
        button_bar = ttk.Frame(dialog, padding=(14, 8))
        button_bar.pack(side=tk.BOTTOM, fill=tk.X)

        body = ttk.Frame(dialog, padding=14)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        tk.Label(body, text=self.tx("Facet colormap:")).grid(row=0, column=0, padx=(0, 12), pady=8, sticky=tk.W)
        cmap = tk.StringVar(value=self.facet_colormap)
        names = ["viridis", "plasma", "inferno", "magma", "cividis", "turbo", "rainbow", "gist_rainbow", "Spectral", "hsv"]
        if _COLORCET_AVAILABLE:
            cet_names = sorted(n for n in plt.colormaps() if n.startswith("cet_"))
            names.extend(cet_names)
        ttk.Combobox(body, textvariable=cmap, values=names, state="readonly", width=34).grid(row=0, column=1, pady=8, sticky="ew")

        diagnostics = None
        try:
            diagnostics = self.i18n.diagnostics()
        except Exception as exc:
            self.log(
                "Warning: could not read i18n diagnostics: "
                "{}: {}".format(type(exc).__name__, exc)
            )

        if diagnostics:
            status = "Locales: {} | {}".format(
                ", ".join(diagnostics.get("available") or []) or "none",
                diagnostics.get("locales_dir", "")
            )
            tk.Label(body, text=status, fg="#555555", anchor=tk.W, justify=tk.LEFT, wraplength=560).grid(row=1, column=0, columnspan=2, pady=(6, 2), sticky="ew")
            if diagnostics.get("errors"):
                tk.Label(body, text=diagnostics["errors"][0], fg="#9b2226", anchor=tk.W, justify=tk.LEFT, wraplength=560).grid(row=2, column=0, columnspan=2, pady=2, sticky="ew")

        def apply():
            self.facet_colormap = cmap.get() or "turbo"
            self._save_method_settings()
            dialog.destroy()

        tk.Button(button_bar, text=self.tx("Apply"), command=apply, bg="#d1e7dd").pack(side=tk.RIGHT, ipadx=24, ipady=3)

        dialog.update_idletasks()
        width = min(680, max(500, dialog.winfo_reqwidth()))
        height = min(700, max(230, dialog.winfo_reqheight()))
        dialog.geometry("{}x{}".format(width, height))
        dialog.minsize(width, height)

    def _get_code_display(self, code):
        return str(code or "en").replace("_", "-").upper()

    def _language_menu_label(self):
        return self._get_code_display(self.language)

    def _select_language_from_menu(self, code):
        self.set_language(code, restart_required=True)

    def _rebuild_language_menu(self):
        self.language_menu.delete(0, tk.END)
        choices = self.i18n.language_names()
        self.language_menu_var.set(self.language)
        for code, native_name in choices:
            code_display = self._get_code_display(code)
            label = f"{code_display} - {native_name}"
            self.language_menu.add_radiobutton(
                label=label, value=code, variable=self.language_menu_var,
                command=lambda selected=code: self._select_language_from_menu(selected)
            )

    def _build_menu(self):
        """Build the compact top bar: Tools, Settings, language and About."""
        self.menu_bar = tk.Menu(self.root)

        self.tools_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.tools_menu.add_command(label=self.tx("Normal Colour Optimisation..."), command=self.open_normal_colour_optimisation, state=tk.DISABLED)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(label=self.tx("Normal Spacing..."), command=self.open_normal_spacing_tool, state=tk.DISABLED)
        self.tools_menu.add_command(label=self.tx("Persistence..."), command=self.open_persistence_tool, state=tk.DISABLED)
        self.tools_menu_index = 0
        self.menu_bar.add_cascade(label=self.tx("Tools"), menu=self.tools_menu)

        self.settings_menu_index = 1
        self.menu_bar.add_command(label=self.tx("Settings"), command=self.show_settings)

        self.language_menu_var = tk.StringVar(value=self.language)
        self.language_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.language_menu_index = 2
        self.menu_bar.add_cascade(label=self._language_menu_label(), menu=self.language_menu)
        self._rebuild_language_menu()

        self.about_menu_index = 3
        self.menu_bar.add_command(label=self.tx("About"), command=self.show_about)
        self.root.config(menu=self.menu_bar)

    def _refresh_menu_language(self):
        """Refresh labels and the available-language list after each reload."""
        try:
            self.menu_bar.entryconfig(self.tools_menu_index, label=self.tx("Tools"))
            self.menu_bar.entryconfig(self.settings_menu_index, label=self.tx("Settings"))
            self.menu_bar.entryconfig(self.language_menu_index, label=self._language_menu_label())
            self.menu_bar.entryconfig(self.about_menu_index, label=self.tx("About"))
            self.tools_menu.entryconfig(0, label=self.tx("Normal Colour Optimisation..."))
            for index, key in zip((2, 3), ("Normal Spacing...", "Persistence...")):
                self.tools_menu.entryconfig(index, label=self.tx(key))
            self._rebuild_language_menu()
        except Exception:
            pass

    def show_about(self):
        about = tk.Toplevel(self.root)
        about.after_idle(lambda w=about: self._translate_widget_tree(w))
        about.title(self.tr("about.title"))
        about.geometry("650x570")
        about.resizable(True, True)
        about.attributes("-topmost", True)
        about.grab_set()

        tk.Label(
            about, text=self.tx("DSE - Discontinuity Set Extractor"),
            font=("Helvetica", 12, "bold")
        ).pack(pady=(14, 2))
        tk.Label(
            about, text=self.tr("about.subtitle"),
            font=("Helvetica", 9, "italic")
        ).pack(pady=(0, 10))

        info_frame = tk.Frame(about)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=16)

        about_text = self.tr("about.body", version=DSE_VERSION)

        txt = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, font=("Helvetica", 9), height=22
        )
        # Keep the About window deliberately simple and robust: the complete
        # translated text is inserted directly, including all references/URLs.
        txt.insert(tk.END, about_text)
        txt.config(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)

        tk.Button(
            about, text=self.tx("Close"),
            command=about.destroy, width=12
        ).pack(pady=10)

    def _build_ui(self):
        deg_str = "deg"

        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(6, 3))

        left_frame = ttk.Frame(self.main_paned, width=540)
        right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(left_frame, weight=1)
        self.main_paned.add(right_frame, weight=1)
        self.root.after_idle(lambda: self.main_paned.sashpos(0, 540))

        # ---------------------------------------------------------
        # LEFT PANEL: THREE-STEP WORKFLOW
        # ---------------------------------------------------------
        style = ttk.Style(self.root)
        style.configure("DSE.TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 9, "bold"))
        style.configure("DSE.TLabelframe.Label", font=("Segoe UI", 9, "bold"))

        # Step 0: Cloud Check Header
        f_cloud_hdr = tk.Frame(left_frame, bg="#e9ecef", bd=1, relief=tk.SOLID)
        f_cloud_hdr.pack(fill=tk.X, pady=(2, 6), padx=2)
        
        f_cloud_hdr.grid_columnconfigure(0, weight=1)
        f_cloud_hdr.grid_columnconfigure(1, weight=0, minsize=68)
        self.lbl_cloud_status = tk.Label(
            f_cloud_hdr, text=self.tr("gui.status_checking"),
            font=("Segoe UI", 9, "bold"), bg="#e9ecef", fg="#495057",
            anchor=tk.W, justify=tk.LEFT, wraplength=370, padx=8, pady=7
        )
        self.lbl_cloud_status.grid(
            row=0, column=0, sticky="nsew", padx=(2, 6), pady=2
        )

        self.btn_refresh_cloud = tk.Button(
            f_cloud_hdr, text="", command=self.refresh_selected_cloud,
            width=58, height=54, padx=3, pady=3,
            relief=tk.RAISED, bg="#ffffff"
        )
        self.btn_refresh_cloud.grid(
            row=0, column=1, sticky="e", padx=(0, 5), pady=4
        )

        self.workflow_notebook = ttk.Notebook(
            left_frame, style="DSE.TNotebook"
        )
        self.workflow_notebook.pack(
            fill=tk.BOTH, expand=True, padx=2, pady=(0, 2)
        )
        self.step1_tab = ttk.Frame(self.workflow_notebook, padding=8)
        self.step2_tab = ttk.Frame(self.workflow_notebook, padding=8)
        self.step3_tab = ttk.Frame(self.workflow_notebook, padding=8)
        self.workflow_notebook.add(
            self.step1_tab, text=self.tr("gui.step1")
        )
        self.workflow_notebook.add(
            self.step2_tab, text=self.tr("gui.step2"), state="disabled"
        )
        self.workflow_notebook.add(
            self.step3_tab, text=self.tr("gui.step3"), state="disabled"
        )

        # Step 1: Colour-code 3D point cloud, then Principal poles.
        # Block 1: Colour-code the 3D point cloud from the selected pole space.
        colour_frame = ttk.LabelFrame(
            self.step1_tab, text=" " + self.tr("gui.colour_code_3dpc") + " ",
            padding=6
        )
        colour_frame.pack(fill=tk.X, padx=4, pady=(4, 3))

        f_space = tk.Frame(colour_frame)
        f_space.pack(fill=tk.X, pady=2)
        tk.Label(f_space, text=self.tr("poles.source.label")).pack(side=tk.LEFT, padx=5)
        self.pole_space_var = tk.StringVar(master=self.root, value="original")
        self.pole_space_combo = ttk.Combobox(
            f_space, textvariable=self.pole_space_var,
            values=("original", "rotated"), state="disabled", width=18
        )
        self.pole_space_combo.pack(side=tk.RIGHT, padx=5)
        self.add_tooltip(self.pole_space_combo, "tip.poles.source")

        f_colour_space = tk.Frame(colour_frame)
        f_colour_space.pack(fill=tk.X, pady=2)
        tk.Label(f_colour_space, text=self.tr("colour.space")).pack(side=tk.LEFT, padx=5)
        self.principal_colour_space_var = tk.StringVar(master=self.root, value="HSV")
        self.principal_colour_space_combo = ttk.Combobox(
            f_colour_space, textvariable=self.principal_colour_space_var,
            values=("HSV", "CIELAB", "CIELCH", "CIELCHmod", "OKLCH", "HSLuv"),
            state="readonly", width=18
        )
        self.principal_colour_space_combo.pack(side=tk.RIGHT, padx=5)
        self.add_tooltip(self.principal_colour_space_combo, "tip.colour.space")

        f_lightness = tk.Frame(colour_frame)
        f_lightness.pack(fill=tk.X, pady=2)
        tk.Label(f_lightness, text=self.tr("colour.lightness")).pack(side=tk.LEFT, padx=5)
        self.principal_colour_lightness_var = tk.StringVar(master=self.root, value="80")
        self.principal_colour_lightness_entry = tk.Entry(
            f_lightness, textvariable=self.principal_colour_lightness_var, width=8
        )
        self.principal_colour_lightness_entry.pack(side=tk.RIGHT, padx=5)
        self.add_tooltip(self.principal_colour_lightness_entry, "tip.colour.lightness")

        self.btn_generate_colour_cloud = self._make_icon_button_v030(
            colour_frame, "imagen_HSV_icono",
            self.generate_principal_colour_cloud,
            "tip.export_hsv", self.tr("gui.generate_colour_cloud")
        )
        self.btn_generate_colour_cloud.configure(state=tk.DISABLED)
        self.btn_generate_colour_cloud.pack(side=tk.LEFT, padx=5, pady=(4, 2))

        # Step 1: Principal poles.
        self.grp_step1 = ttk.LabelFrame(
            self.step1_tab, text=" " + self.tr("gui.principal_poles") + " ",
            style="DSE.TLabelframe"
        )
        self.grp_step1.pack(fill=tk.X, pady=3, padx=2)

        f_proj = tk.Frame(self.grp_step1)
        f_proj.pack(fill=tk.X, pady=2)
        tk.Label(f_proj, text=self.tr("gui.projection")).pack(side=tk.LEFT, padx=5)
        self.proj_combo = ttk.Combobox(
            f_proj, values=[self.tx("projection.equal_angle"), self.tx("projection.equal_area"), self.tx("projection.equal_proportion")],
            state="readonly", width=16
        )
        self.proj_combo.current(0)
        self.proj_combo.pack(side=tk.RIGHT, padx=5)

        f_bins = tk.Frame(self.grp_step1)
        f_bins.pack(fill=tk.X, pady=2)
        tk.Label(f_bins, text=self.tr("gui.bins")).pack(side=tk.LEFT, padx=5)
        self.spin_bins = tk.Spinbox(f_bins, from_=6, to=10, width=6)
        self.spin_bins.delete(0, "end")
        self.spin_bins.insert(0, "6")
        self.spin_bins.pack(side=tk.RIGHT, padx=5)

        f_ang = tk.Frame(self.grp_step1)
        f_ang.pack(fill=tk.X, pady=2)
        tk.Label(f_ang, text=self.tr("gui.min_separ_angle", deg_str=deg_str)).pack(side=tk.LEFT, padx=5)
        self.spin_angle = tk.Spinbox(f_ang, from_=5, to=90, width=6)
        self.spin_angle.delete(0, "end")
        self.spin_angle.insert(0, "30")
        self.spin_angle.pack(side=tk.RIGHT, padx=5)

        f_maxp = tk.Frame(self.grp_step1)
        f_maxp.pack(fill=tk.X, pady=2)
        tk.Label(f_maxp, text=self.tr("gui.max_poles")).pack(side=tk.LEFT, padx=5)
        self.spin_maxpoles = tk.Spinbox(f_maxp, from_=1, to=20, width=6)
        self.spin_maxpoles.delete(0, "end")
        self.spin_maxpoles.insert(0, "5")
        self.spin_maxpoles.pack(side=tk.RIGHT, padx=5)

        f_style = tk.Frame(self.grp_step1)
        f_style.pack(fill=tk.X, pady=2)
        tk.Label(f_style, text=self.tr("gui.density_style")).pack(side=tk.LEFT, padx=5)
        self.style_combo = ttk.Combobox(
            f_style, values=[self.tx("gui.contour_lines"), self.tx("gui.filled_contours")],
            state="readonly", width=16
        )
        self.style_combo.current(0)
        self.style_combo.pack(side=tk.RIGHT, padx=5)

        self.labeled_var = tk.IntVar(value=1)
        self.chk_labels = tk.Checkbutton(self.grp_step1, text=self.tr("Show stereonet labels"), variable=self.labeled_var)
        self.chk_labels.pack(pady=1)

        self.btn_poles = tk.Button(
            self.grp_step1, text=self.tr("Plot Poles on Stereonet"), 
            command=self.run_plot_poles, bg="#e1e1e1", height=1
        )
        self.btn_poles.pack(fill=tk.X, padx=5, pady=2)

        self.btn_density = tk.Button(
            self.grp_step1, text=self.tr("Calculate Density & Principal Poles"), 
            command=self.run_plot_density, bg="#d1e7dd", height=2, font=("Helvetica", 9, "bold")
        )
        self.btn_density.pack(fill=tk.X, padx=5, pady=3)

        self.btn_show_density = tk.Button(
            self.grp_step1, text=self.tr("Show Computed Density"),
            command=self.run_show_density, bg="#d9eef9", height=1,
            state=tk.DISABLED
        )
        self.btn_show_density.pack(fill=tk.X, padx=5, pady=3)

        # Step 2: Family Classification Group
        self.grp_step2 = ttk.LabelFrame(
            self.step2_tab, text=" " + self.tr("gui.step2") + " ",
            style="DSE.TLabelframe"
        )
        self.grp_step2.pack(fill=tk.X, pady=3, padx=2)

        f_js_cone = tk.Frame(self.grp_step2)
        f_js_cone.pack(fill=tk.X, pady=2)
        tk.Label(f_js_cone, text=self.tx("DS Cone Threshold (deg):")).pack(side=tk.LEFT, padx=5)
        self.spin_js_cone = tk.Spinbox(f_js_cone, from_=1.0, to=90.0, increment=1.0, width=6)
        self.spin_js_cone.delete(0, "end")
        self.spin_js_cone.insert(0, "30.0")
        self.spin_js_cone.pack(side=tk.RIGHT, padx=5)

        self.btn_classify_js = tk.Button(
            self.grp_step2, text=self.tr("Classify Point Cloud (DS Field)"), 
            command=self.run_classify_js, bg="#cfe2ff", height=2, font=("Helvetica", 9, "bold")
        )
        self.btn_classify_js.pack(fill=tk.X, padx=5, pady=3)

        self.btn_poles_by_family = tk.Button(
            self.grp_step2, text=self.tr("Plot Poles by Family (DS)"),
            command=self.run_plot_poles_by_family, bg="#e1e1e1", height=1
        )
        self.btn_poles_by_family.pack(fill=tk.X, padx=5, pady=2)

                # Step 3: Spatial Clustering & Plane Fitting
        self.grp_step3 = ttk.LabelFrame(
            self.step3_tab, text=self.tx("Spatial clustering and plane fitting"),
            style="DSE.TLabelframe"
        )
        self.grp_step3.pack(fill=tk.X, pady=3, padx=2)

        self.cluster_parameters = ttk.LabelFrame(self.grp_step3, text=" " + self.tr("Cluster analysis") + " ")
        self.cluster_parameters.pack(fill=tk.X, padx=4, pady=(4, 3))
        f_kknn = tk.Frame(self.cluster_parameters)
        f_kknn.pack(fill=tk.X, pady=2)
        tk.Label(f_kknn, text=self.tx("K-th Neighbor (K):")).pack(side=tk.LEFT, padx=5)
        self.spin_k_neighbor = tk.Spinbox(f_kknn, from_=1, to=50, increment=1, width=6)
        self.spin_k_neighbor.delete(0, "end")
        self.spin_k_neighbor.insert(0, "4")
        self.spin_k_neighbor.pack(side=tk.RIGHT, padx=5)

        f_ksig = tk.Frame(self.cluster_parameters)
        f_ksig.pack(fill=tk.X, pady=2)
        tk.Label(f_ksig, text=self.tx("Sigma Multiplier (k_sigma):")).pack(side=tk.LEFT, padx=5)
        self.spin_k_sigma = tk.Spinbox(f_ksig, from_=0.1, to=10.0, increment=0.5, width=6)
        self.spin_k_sigma.delete(0, "end")
        self.spin_k_sigma.insert(0, "2.0")
        self.spin_k_sigma.pack(side=tk.RIGHT, padx=5)

        f_dbscan_minpts = tk.Frame(self.cluster_parameters)
        f_dbscan_minpts.pack(fill=tk.X, pady=2)
        tk.Label(f_dbscan_minpts, text=self.tr("gui.dbscan_minpts")).pack(side=tk.LEFT, padx=5)
        self.spin_dbscan_minpts = tk.Spinbox(f_dbscan_minpts, from_=2, to=100, increment=1, width=6)
        self.spin_dbscan_minpts.pack(side=tk.RIGHT, padx=5)

        f_mincluster = tk.Frame(self.cluster_parameters)
        f_mincluster.pack(fill=tk.X, pady=2)
        tk.Label(f_mincluster, text=self.tr("gui.min_cluster_size")).pack(side=tk.LEFT, padx=5)
        self.spin_min_cluster_size = tk.Spinbox(f_mincluster, from_=1, to=1000000, increment=10, width=8)
        self.spin_min_cluster_size.pack(side=tk.RIGHT, padx=5)

        self.plane_parameters = ttk.LabelFrame(self.grp_step3, text=" " + self.tr("Plane calculation") + " ")
        self.plane_parameters.pack(fill=tk.X, padx=4, pady=3)
        f_merge = tk.Frame(self.plane_parameters)
        f_merge.pack(fill=tk.X, pady=2)
        tk.Label(f_merge, text=self.tr("gui.merge")).pack(side=tk.LEFT, padx=5)
        self.spin_merge_sigma = tk.Spinbox(f_merge, from_=0.0, to=10.0, increment=0.1, width=6)
        self.spin_merge_sigma.delete(0, "end")
        self.spin_merge_sigma.insert(0, "1.5")
        self.spin_merge_sigma.pack(side=tk.RIGHT, padx=5)

        self.fix_orientation_var = tk.IntVar(value=1)
        self.chk_fix_orientation = tk.Checkbutton(
            self.plane_parameters, text=self.tr("gui.fix_orientation"),
            variable=self.fix_orientation_var
        )
        self.chk_fix_orientation.pack(pady=1)
        self.add_tooltip(self.chk_fix_orientation, "tip.fix")

        f_sort = tk.Frame(self.plane_parameters)
        f_sort.pack(fill=tk.X, pady=2)
        tk.Label(f_sort, text=self.tr("gui.sort")).pack(side=tk.LEFT, padx=5)
        self.sort_combo = ttk.Combobox(
            f_sort, values=["Size (largest first)", "D (spatial order)", "Random"],
            state="readonly", width=20
        )
        self.sort_combo.current(0)
        self.sort_combo.pack(side=tk.RIGHT, padx=5)

        f_seed = tk.Frame(self.plane_parameters)
        f_seed.pack(fill=tk.X, pady=2)
        tk.Label(f_seed, text=self.tr("gui.seed")).pack(side=tk.LEFT, padx=5)
        self.ent_random_seed = tk.Entry(f_seed, width=8)
        self.ent_random_seed.pack(side=tk.RIGHT, padx=5)

        self.btn_clusterize = tk.Button(
            self.grp_step3, text=self.tr("Clusterize"),
            command=self.run_clusterize, bg="#e2d9f3", height=2, font=("Helvetica", 9, "bold")
        )
        self.btn_clusterize.pack(fill=tk.X, padx=5, pady=4)

        self.facet_export = ttk.LabelFrame(self.grp_step3, text=" " + self.tr("Facet export") + " ")
        self.facet_export.pack(fill=tk.X, padx=4, pady=3)
        self.export_family_clouds_var = tk.IntVar(value=1)
        self.chk_export_family_clouds = tk.Checkbutton(
            self.facet_export,
            text=self.tr("Export one patch per DS family with Cluster id active"),
            variable=self.export_family_clouds_var, anchor=tk.W,
            justify=tk.LEFT, wraplength=330
        )
        self.chk_export_family_clouds.pack(fill=tk.X, padx=5, pady=(2, 4))

        self.create_cluster_clouds_var = tk.IntVar(value=1)
        self.chk_create_cluster_clouds = tk.Checkbutton(
            self.facet_export, text=self.tr("Create separate cluster clouds"),
            variable=self.create_cluster_clouds_var
        )
        self.chk_create_cluster_clouds.pack(pady=1)
        self.add_tooltip(self.chk_create_cluster_clouds, "tip.clouds")
        facet_options = tk.Frame(self.facet_export)
        facet_options.pack(fill=tk.X, padx=5, pady=(3, 1))
        tk.Label(facet_options, text=self.tr("gui.facet_shape")).pack(side=tk.LEFT)
        self.facet_type_var = tk.StringVar(value="convex")
        self.facet_type_combo = ttk.Combobox(
            facet_options, textvariable=self.facet_type_var,
            values=("convex", "disk", "ellipse", "rectangle"),
            state="readonly", width=14
        )
        self.facet_type_combo.pack(side=tk.RIGHT)
        self.btn_facets = tk.Button(
            self.facet_export, text=self.tr("Create Cluster Facets"),
            command=self.create_cluster_facets, bg="#d1ecf1", height=2,
            font=("Helvetica", 9, "bold"), state=tk.DISABLED
        )
        self.btn_facets.pack(fill=tk.X, padx=5, pady=4)

                # ---------------------------------------------------------
        # RIGHT PANEL: Notebook with two tabs + log console
        # ---------------------------------------------------------
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(2, 4))

        # --- Tab 1: Principal Poles ---
        tab_poles = ttk.Frame(self.notebook)
        self.notebook.add(tab_poles, text=self.tr("Principal Poles"))

        # Block 2: Principal poles calculation and editing.
        self.poles_frame = ttk.LabelFrame(
            tab_poles, text=" " + self.tr("gui.principal_pole_analysis") + " ",
            padding=6
        )
        self.poles_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(3, 4))

        tk.Label(self.poles_frame, text=self.tx("Principal Poles Summary"), font=("Helvetica", 10, "bold")).pack(anchor=tk.W, pady=(0, 2))
        self.lbl_poles_status = tk.Label(
            self.poles_frame, text=self.tr("status.empty"), anchor=tk.W,
            bg="#f2f2f7", fg="#6c757d", padx=8, pady=4
        )
        self.lbl_poles_status.pack(fill=tk.X, pady=(0, 4))

        tree_frame = ttk.Frame(self.poles_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        self.tree = ttk.Treeview(
            tree_frame, columns=("ID", "DipDir", "Dip", "Density", "FisherK", "N"), show="headings", height=6
        )
        self.tree.heading("ID", text=self.tr("table.id"))
        self.tree.heading("DipDir", text=self.tr("table.dip_direction"))
        self.tree.heading("Dip", text=self.tr("table.dip"))
        self.tree.heading("Density", text=self.tr("table.density"))
        self.tree.heading("FisherK", text=self.tr("table.fisher_k"))
        self.tree.heading("N", text=self.tr("table.sample_count"))
        self.tree.column("ID", width=48, anchor=tk.CENTER)
        self.tree.column("DipDir", width=95, anchor=tk.CENTER)
        self.tree.column("Dip", width=85, anchor=tk.CENTER)
        self.tree.column("Density", width=82, anchor=tk.CENTER)
        self.tree.column("FisherK", width=75, anchor=tk.CENTER)
        self.tree.column("N", width=70, anchor=tk.CENTER)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_pole_select)

        edit_frame = ttk.LabelFrame(self.poles_frame, text=self.tr("gui.selected_pole"))
        edit_frame.pack(fill=tk.X, pady=5)
        tk.Label(edit_frame, text=self.tr("gui.dip_dir")).grid(row=0, column=0, padx=4, pady=4)
        self.ent_dipdir = tk.Entry(edit_frame, width=8)
        self.ent_dipdir.grid(row=0, column=1, padx=4, pady=4)
        tk.Label(edit_frame, text=self.tr("gui.dip")).grid(row=0, column=2, padx=4, pady=4)
        self.ent_dip = tk.Entry(edit_frame, width=8)
        self.ent_dip.grid(row=0, column=3, padx=4, pady=4)
        self.btn_apply_edit = tk.Button(edit_frame, text=self.tr("gui.apply_changes"), command=self.action_update_pole, bg="#fff3cd")
        self.btn_apply_edit.grid(row=0, column=4, padx=6, pady=4)

        btn_box = tk.Frame(self.poles_frame)
        btn_box.pack(fill=tk.X, pady=2)
        self.btn_mup = tk.Button(btn_box, text=self.tr("gui.move_up"), command=self.action_move_up, width=10)
        self.btn_mup.pack(side=tk.LEFT, padx=2)
        self.btn_mdown = tk.Button(btn_box, text=self.tr("gui.move_down"), command=self.action_move_down, width=10)
        self.btn_mdown.pack(side=tk.LEFT, padx=2)
        self.btn_addp = tk.Button(btn_box, text=self.tr("gui.add_pole"), command=self.action_add_pole, width=10)
        self.btn_addp.pack(side=tk.LEFT, padx=2)
        self.btn_delp = tk.Button(btn_box, text=self.tr("gui.delete_pole"), command=self.action_delete_pole, width=11, bg="#f8d7da")
        self.btn_delp.pack(side=tk.LEFT, padx=2)

        # --- Tab 2: Pairwise angular separation (read-only) ---
        self.tab_pairwise = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_pairwise, text=self.tr("pairwise.title"), state="disabled")
        tk.Label(
            self.tab_pairwise, text=self.tr("pairwise.description"),
            anchor=tk.W, justify=tk.LEFT
        ).pack(fill=tk.X, padx=8, pady=(8, 4))
        pair_frame = ttk.Frame(self.tab_pairwise)
        pair_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.pairwise_tree = ttk.Treeview(pair_frame, show="headings", height=12)
        pair_y = ttk.Scrollbar(pair_frame, orient=tk.VERTICAL, command=self.pairwise_tree.yview)
        pair_x = ttk.Scrollbar(pair_frame, orient=tk.HORIZONTAL, command=self.pairwise_tree.xview)
        self.pairwise_tree.configure(yscrollcommand=pair_y.set, xscrollcommand=pair_x.set)
        self.pairwise_tree.grid(row=0, column=0, sticky="nsew")
        pair_y.grid(row=0, column=1, sticky="ns")
        pair_x.grid(row=1, column=0, sticky="ew")
        pair_frame.rowconfigure(0, weight=1); pair_frame.columnconfigure(0, weight=1)

        # --- Tab 3: Cluster Planes (disabled until computed) ---
        self.tab_planes = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_planes, text=self.tr("Cluster Planes"), state="disabled")

        tk.Label(self.tab_planes, text=self.tx("Cluster Planes Summary"), font=("Helvetica", 10, "bold")).pack(anchor=tk.W, pady=(5, 2))

        planes_frame = ttk.Frame(self.tab_planes)
        planes_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        self.planes_tree = ttk.Treeview(
            planes_frame,
            columns=("Family", "Cl", "DipDir", "Dip", "A", "B", "C", "D", "Size"),
            show="headings", height=10
        )
        for col, w in [("Family",80),("Cl",70),("DipDir",115),("Dip",90),
                        ("A",90),("B",90),("C",90),("D",100),("Size",100)]:
            self.planes_tree.heading(col, text=col)
            self.planes_tree.column(col, width=w, minwidth=w, anchor=tk.CENTER, stretch=True)

        planes_scroll = ttk.Scrollbar(planes_frame, orient=tk.VERTICAL, command=self.planes_tree.yview)
        self.planes_tree.configure(yscroll=planes_scroll.set)
        self.planes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        planes_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Tab 4: dispersion of fitted cluster normals by DS family ---
        self.tab_cluster_fisher = ttk.Frame(self.notebook)
        self.notebook.add(
            self.tab_cluster_fisher, text=self.tr("Mean Pole (Fisher)"), state="disabled"
        )
        fisher_controls = ttk.Frame(self.tab_cluster_fisher)
        fisher_controls.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(fisher_controls, text=self.tr("gui.confidence_circle")).pack(side=tk.LEFT)
        self.fisher_confidence_var = tk.StringVar(value="95%")
        confidence_combo = ttk.Combobox(
            fisher_controls, textvariable=self.fisher_confidence_var,
            values=("None", "63%", "95%"), state="readonly", width=8
        )
        confidence_combo.pack(side=tk.LEFT, padx=(6, 12))
        confidence_combo.bind(
            "<<ComboboxSelected>>", self._refresh_cluster_fisher_table
        )
        ttk.Button(
            fisher_controls, text=self.tr("gui.plot_stereonet"),
            command=self.plot_cluster_fisher_stereonet
        ).pack(side=tk.LEFT)

        fisher_frame = ttk.Frame(self.tab_cluster_fisher)
        fisher_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.cluster_fisher_tree = ttk.Treeview(
            fisher_frame,
            columns=("Family", "DipDir", "Dip", "N", "K", "MaxDev", "Confidence"),
            show="headings", height=10
        )
        for column, heading, width in (
                ("Family", "DS", 75), ("DipDir", "Dip Dir. (deg)", 115),
                ("Dip", "Dip (deg)", 95), ("N", "Clusters", 80),
                ("K", "Fisher K", 90), ("MaxDev", "Max deviation (deg)", 145),
                ("Confidence", "Confidence (deg)", 125)):
            self.cluster_fisher_tree.heading(column, text=heading)
            self.cluster_fisher_tree.column(
                column, width=width, minwidth=width, anchor=tk.CENTER
            )
        fisher_scroll = ttk.Scrollbar(
            fisher_frame, orient=tk.VERTICAL,
            command=self.cluster_fisher_tree.yview
        )
        self.cluster_fisher_tree.configure(yscrollcommand=fisher_scroll.set)
        self.cluster_fisher_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fisher_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Permanent horizontal execution log below the full workspace.
        self.log_frame = ttk.LabelFrame(
            self.root,
            text=self.tr("gui.execution_log")
        )
        self.log_frame.pack(
            side=tk.BOTTOM, fill=tk.X, padx=6, pady=(3, 6)
        )
        self.txt_log = scrolledtext.ScrolledText(
            self.log_frame, font=("Consolas", 9), state=tk.DISABLED,
            height=7, wrap=tk.NONE
        )
        self.txt_log.pack(fill=tk.X, expand=False, padx=6, pady=5)

    # ---------------------------------------------------------
    # WORKFLOW AND STATE CONTROL (SMART DEPENDENCIES)
    # ---------------------------------------------------------
    def _analysis_cloud(self):
        cloud = self.get_selected_cloud()
        if cloud is None:
            return None
        required = ("Discontinuity Set (DS)", "Cluster id (cl)", "A", "B", "C", "D")
        missing = [name for name in required
                   if cloud.getScalarFieldIndexByName(name) < 0]
        if missing:
            messagebox.showwarning(
                self.tr("Tools"), self.tr("gui.missing_scalar_fields_detail", fields=", ".join(missing))
            )
            return None
        return cloud

    def _tool_families(self, cloud):
        index = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
        values = np.asarray(cloud.getScalarField(index).asArray(), dtype=int)
        return [int(value) for value in np.unique(values) if value > 0]

    def _save_spacing_result(self, result, folder):
        family = result["family_id"]
        header = "DiscontinuitySet\tInitialPlane\tFinalPlane\tSpacing\tD1\tD2"
        np.savetxt(os.path.join(folder, f"ds-{family}-nfp-plane1-plane2-s-D1-D2.txt"),
                   result["nonpersistent_raw"], delimiter="\t", header=header,
                   comments="", fmt="%.8g")
        np.savetxt(os.path.join(folder, f"ds-{family}-fp-plane1-plane2-s-D1-D2.txt"),
                   result["full_persistent_raw"], delimiter="\t", header=header,
                   comments="", fmt="%.8g")

    def _analysis_grid_shape(self, item_count):
        """Return a compact rows x columns layout for analysis figures."""
        count = max(1, int(item_count))
        if count == 1:
            return 1, 1
        if count == 2:
            return 1, 2
        if count <= 4:
            return 2, 2
        if count <= 6:
            return 3, 2
        if count <= 9:
            return 3, 3
        columns = int(np.ceil(np.sqrt(count)))
        rows = int(np.ceil(count / columns))
        return rows, columns

    def _create_analysis_figure(self, item_count, window_title):
        """Create a readable analysis figure with an adaptive subplot grid."""
        rows, columns = self._analysis_grid_shape(item_count)
        subplot_width = 5.2 if columns <= 2 else 4.6
        subplot_height = 4.0 if rows <= 2 else 3.7
        figure_width = min(16.0, max(7.2, columns * subplot_width))
        figure_height = min(12.0, max(4.8, rows * subplot_height))
        figure, axes = plt.subplots(
            rows, columns,
            figsize=(figure_width, figure_height),
            squeeze=False,
            constrained_layout=True
        )
        try:
            figure.canvas.manager.set_window_title(window_title)
        except Exception:
            pass
        flat_axes = axes.ravel()
        for axis in flat_axes[item_count:]:
            axis.set_visible(False)
        return figure, flat_axes[:item_count]

    def _format_analysis_axis(self, axis):
        """Apply consistent typography and spacing to analysis subplots."""
        axis.tick_params(axis="both", labelsize=8)
        axis.xaxis.label.set_size(9)
        axis.yaxis.label.set_size(9)
        axis.title.set_fontsize(9)
        axis.title.set_fontweight("bold")
        axis.title.set_wrap(True)
        axis.grid(True, alpha=0.18, linewidth=0.6)

    def _show_result_table(self, title, columns, rows, save_callback=None):
        window = tk.Toplevel(self.root)
        window.after_idle(lambda w=window: self._translate_widget_tree(w))
        window.title(title)
        window.geometry("1050x480")
        window.resizable(True, True)
        notebook = ttk.Notebook(window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tab = ttk.Frame(notebook)
        notebook.add(tab, text=self.tr("Results"))
        tree = ttk.Treeview(tab, columns=columns, show="headings")
        ybar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=tree.yview)
        xbar = ttk.Scrollbar(tab, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        tab.rowconfigure(0, weight=1); tab.columnconfigure(0, weight=1)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=110, anchor=tk.CENTER)
        for row in rows:
            tree.insert("", tk.END, values=row)
        if save_callback is not None:
            button_bar = ttk.Frame(window)
            button_bar.pack(fill=tk.X, padx=8, pady=(0, 8))
            ttk.Button(
                button_bar, text=self.tr("gui.save_results_txt"),
                command=save_callback
            ).pack(side=tk.RIGHT)
        return window

    def open_normal_colour_optimisation(self):
        """Optimise the colour reference system and inspect/export the result."""
        cloud = self.get_selected_cloud()
        if cloud is None or not cloud.hasNormals():
            messagebox.showwarning(
                self.tr("dialog.warning_title"),
                self.tr("colour.error.normals"), parent=self.root
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("colour.title"))
        dialog.transient(self.root)
        dialog.resizable(True, True)

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        defaults = {
            "dof": "3",
            "objective": "rational_vertical_asymptote",
            "subsample": "25",
            "iterations": "80",
            "population": "12",
            "seed": "",
            "space": "HSV",
            "lightness": "80",
        }
        # Reopen the tool in the state of the last completed optimisation.
        if self.optimised_colour_angles is not None:
            defaults["dof"] = str(len(self.optimised_colour_angles))
        if self.optimised_colour_objective_name in colour_opt.OBJECTIVES:
            defaults["objective"] = self.optimised_colour_objective_name
        variables = {
            key: tk.StringVar(master=dialog, value=value)
            for key, value in defaults.items()
        }
        rows = (
            ("colour.dof", "dof", ("2", "3")),
            ("colour.objective", "objective", colour_opt.OBJECTIVES),
            ("colour.subsample", "subsample", None),
            ("colour.iterations", "iterations", None),
            ("colour.population", "population", None),
            ("colour.seed", "seed", None),
            ("colour.space", "space", ("HSV", "CIELAB", "CIELCH", "CIELCHmod", "OKLCH", "HSLuv")),
            ("colour.lightness", "lightness", None),
        )
        controls = {}
        for row, (label_key, key, choices) in enumerate(rows):
            ttk.Label(frame, text=self.tr(label_key)).grid(
                row=row, column=0, sticky=tk.W, padx=(0, 14), pady=5
            )
            if choices is not None:
                control = ttk.Combobox(
                    frame, textvariable=variables[key], values=choices,
                    state="readonly", width=36
                )
                control.set(defaults[key])
            else:
                control = ttk.Entry(
                    frame, textvariable=variables[key], width=38
                )
                control.delete(0, tk.END)
                control.insert(0, defaults[key])
            control.grid(row=row, column=1, sticky=tk.EW, pady=5)
            controls[key] = control
            self.add_tooltip(control, "tip.colour." + key)

        state = {"result": None, "rgb": None, "rotated": None, "poles_fig": None, "density_fig": None}

        # Editable result table. The optimisation angles are rotation angles
        # expressed in degrees; the table also allows deliberate manual edits.
        result_box = ttk.LabelFrame(
            frame, text=self.tr("colour.optimisation_result"), padding=8
        )
        result_box.grid(row=8, column=2, sticky=tk.NSEW, padx=(18, 0), pady=(5, 0))
        result_box.columnconfigure(1, weight=1)
        ttk.Label(result_box, text=self.tr("colour.parameter")).grid(
            row=0, column=0, sticky=tk.W, padx=4, pady=2
        )
        ttk.Label(result_box, text=self.tr("colour.value")).grid(
            row=0, column=1, sticky=tk.W, padx=4, pady=2
        )
        ttk.Label(result_box, text=self.tr("colour.unit")).grid(
            row=0, column=2, sticky=tk.W, padx=4, pady=2
        )
        angle_entries = []
        angle_labels = []
        for index in range(3):
            label = ttk.Label(result_box, text=self.tr("colour.rotation_angle", index=index + 1))
            label.grid(row=index + 1, column=0, sticky=tk.W, padx=4, pady=3)
            angle_labels.append(label)
            entry = ttk.Entry(result_box, width=14)
            entry.grid(row=index + 1, column=1, sticky=tk.EW, padx=4, pady=3)
            ttk.Label(result_box, text="deg").grid(
                row=index + 1, column=2, sticky=tk.W, padx=4, pady=3
            )
            self.add_tooltip(entry, "tip.colour.rotation_angle")
            angle_entries.append(entry)

        ttk.Label(result_box, text=self.tr("colour.objective_result")).grid(
            row=5, column=0, sticky=tk.W, padx=4, pady=3
        )
        objective_value_var = tk.StringVar(master=dialog, value="-")
        ttk.Label(result_box, textvariable=objective_value_var).grid(
            row=5, column=1, sticky=tk.W, padx=4, pady=3
        )
        ttk.Label(result_box, text=self.tr("colour.dimensionless")).grid(
            row=5, column=2, sticky=tk.W, padx=4, pady=3
        )

        def update_objective_display(value):
            try:
                objective_value_var.set("{:.8g}".format(float(value)))
            except Exception:
                objective_value_var.set("-")

        def refresh_angle_rows(*_args):
            dof = int(variables["dof"].get())
            euler_keys = ("colour.euler_z", "colour.euler_y", "colour.euler_x")
            for index, entry in enumerate(angle_entries):
                entry.configure(state=tk.NORMAL if index < dof else tk.DISABLED)
                if index >= dof:
                    entry.delete(0, tk.END)
                if dof == 3:
                    angle_labels[index].configure(text=self.tr(euler_keys[index]))
                else:
                    angle_labels[index].configure(
                        text=self.tr("colour.rotation_angle", index=index + 1)
                    )

        def populate_result_table(angles):
            values = np.asarray(angles, dtype=float).ravel()
            for index, entry in enumerate(angle_entries):
                entry.configure(state=tk.NORMAL)
                entry.delete(0, tk.END)
                if index < values.size:
                    entry.insert(0, "{:.6f}".format(values[index]))
            refresh_angle_rows()

        def apply_manual_angles():
            try:
                dof = int(variables["dof"].get())
                angles = np.array([
                    float(angle_entries[index].get()) for index in range(dof)
                ], dtype=float)
                if not np.isfinite(angles).all():
                    raise ValueError(self.tr("colour.error.invalid_angles"))
                normals = np.asarray(cloud.normals(), dtype=np.float64)
                objective_name = variables["objective"].get()
                objective_value = colour_opt.objective_value(
                    angles, normals, objective=objective_name
                )
                rotation = colour_opt.rotation_matrix(angles)
                result = colour_opt.OptimisationResult(
                    angles=angles, rotation=rotation, objective=objective_value,
                    equivalent_degrees=colour_opt.equivalent_degrees(
                        objective_value, objective_name
                    ), evaluations=0, iterations=0, seconds=0.0,
                    success=True, message=self.tr("colour.manual_angles_message")
                )
                state["result"] = result
                self.optimised_colour_rotation = rotation.copy()
                self.optimised_colour_angles = angles.copy()
                self.optimised_colour_objective = float(objective_value)
                self.optimised_colour_objective_name = objective_name
                self.optimised_colour_evaluations = 0
                self.optimised_colour_iterations = 0
                self.optimised_colour_seconds = 0.0
                populate_result_table(angles)
                calculate_colours()
                progress["value"] = 100
                angles_text = ", ".join("{:.3f}".format(value) for value in angles)
                update_objective_display(objective_value)
                result_var.set(self.tr(
                    "colour.result", angles=angles_text,
                    value=objective_value, seconds=0.0
                ))
                for button in (btn_poles, btn_density, btn_export):
                    button.configure(state=tk.NORMAL)
                if self.pole_space_var is not None:
                    self.pole_space_combo.configure(state="readonly")
                self.log(self.tr(
                    "log.colour.manual_angles", angles=angles_text,
                    value=objective_value
                ))
            except Exception as exc:
                messagebox.showerror(
                    self.tr("dialog.error_title"), str(exc), parent=dialog
                )

        ttk.Button(
            result_box, text=self.tr("colour.apply_angles"),
            command=apply_manual_angles
        ).grid(row=6, column=0, columnspan=3, sticky=tk.EW, padx=4, pady=(2, 2))

        result_note = ttk.Label(
            result_box, text=self.tr("colour.angles_unit_note"),
            wraplength=280, justify=tk.LEFT
        )
        result_note.grid(row=7, column=0, columnspan=3, sticky=tk.W, padx=4, pady=(4, 6))
        controls["dof"].bind("<<ComboboxSelected>>", refresh_angle_rows, add="+")

        # Live preview. This is deliberately isolated from the existing
        # optimisation/actions block so all original buttons remain untouched.
        preview_box = ttk.LabelFrame(frame, text=self.tr("colour.space"), padding=8)
        preview_box.grid(row=0, column=2, rowspan=8, sticky=tk.N, padx=(18, 0), pady=5)
        preview_label = ttk.Label(preview_box)
        preview_label.pack()
        preview_state = {"photo": None, "after": None}

        def update_colour_preview(event=None):
            if preview_state["after"] is not None:
                try:
                    dialog.after_cancel(preview_state["after"])
                except Exception:
                    pass
                preview_state["after"] = None
            try:
                level = float(variables["lightness"].get())
            except ValueError:
                return
            try:
                rgb_preview = colour_opt.cylindrical_colour_map_preview(
                    variables["space"].get(), level, size=281
                )

                # Put the colour map beneath the existing Riquelme stereonet.
                # The negative z-order keeps grid lines and labels on top.
                from matplotlib.figure import Figure
                from matplotlib.backends.backend_agg import FigureCanvasAgg
                figure = Figure(figsize=(2.85, 2.85), dpi=100, facecolor="white")
                axis = figure.add_axes((0.14, 0.14, 0.72, 0.72))
                axis.imshow(
                    rgb_preview, extent=(-1.0, 1.0, -1.0, 1.0),
                    origin="upper", interpolation="nearest", zorder=-100
                )
                stereonet.draw_stereonet(
                    axis, projection=self._canonical_projection(), labeled=1
                )
                axis.set_xlim(-1.16, 1.16)
                axis.set_ylim(-1.16, 1.16)
                axis.set_aspect("equal", adjustable="box")
                axis.patch.set_alpha(0.0)
                canvas = FigureCanvasAgg(figure)
                canvas.draw()
                rgb_preview = np.asarray(canvas.buffer_rgba())[..., :3].copy()
                figure.clear()

                if Image is not None and ImageTk is not None:
                    photo = ImageTk.PhotoImage(
                        Image.fromarray(rgb_preview, mode="RGB"), master=dialog
                    )
                else:
                    height, width = rgb_preview.shape[:2]
                    ppm = ("P6\n{} {}\n255\n".format(width, height).encode("ascii")
                           + rgb_preview.tobytes())
                    photo = tk.PhotoImage(
                        master=dialog, data=base64.b64encode(ppm), format="PPM"
                    )
                preview_state["photo"] = photo
                preview_label.configure(image=photo)
            except Exception as exc:
                preview_label.configure(text=str(exc), image="")

        def schedule_colour_preview(*_args):
            if preview_state["after"] is not None:
                try:
                    dialog.after_cancel(preview_state["after"])
                except Exception:
                    pass
            preview_state["after"] = dialog.after(80, update_colour_preview)

        controls["space"].bind("<<ComboboxSelected>>", update_colour_preview, add="+")
        variables["space"].trace_add("write", schedule_colour_preview)
        variables["lightness"].trace_add("write", schedule_colour_preview)
        dialog.after_idle(update_colour_preview)

        result_var = tk.StringVar(master=dialog, value=self.tr("colour.ready"))
        ttk.Label(
            frame, textvariable=result_var, wraplength=650, justify=tk.LEFT
        ).grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(10, 6))

        progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        progress.grid(row=9, column=0, columnspan=2, sticky=tk.EW, pady=5)

        buttons = ttk.Frame(frame)
        buttons.grid(row=10, column=0, columnspan=2, pady=(12, 2))
        def calculate_colours():
            normals = np.asarray(cloud.normals(), dtype=np.float64)
            rgb, rotated = colour_opt.colours_from_normals(
                normals,
                state["result"].angles,
                variables["space"].get(),
                float(variables["lightness"].get()),
                projection=self._canonical_projection(),
            )
            state["rgb"] = rgb
            state["rotated"] = rotated
            return normals, rgb, rotated

        def optimise():
            try:
                normals = np.asarray(cloud.normals(), dtype=np.float64)
                fraction = float(variables["subsample"].get()) / 100.0
                seed_text = variables["seed"].get().strip()
                seed = None if seed_text == "" else int(seed_text)
                progress["value"] = 0
                dialog.update_idletasks()

                def report(current, total, value, convergence):
                    progress["value"] = 100.0 * current / max(total, 1)
                    result_var.set(self.tr(
                        "colour.progress", iteration=current,
                        total=total, value=value
                    ))
                    dialog.update_idletasks()
                    return True

                result = colour_opt.optimise_rotation(
                    normals,
                    degrees_of_freedom=int(variables["dof"].get()),
                    objective=variables["objective"].get(),
                    subsample=fraction,
                    seed=seed,
                    max_iterations=int(variables["iterations"].get()),
                    population_size=int(variables["population"].get()),
                    progress_callback=report,
                )
                state["result"] = result
                self.optimised_colour_rotation = np.asarray(result.rotation, dtype=np.float64).copy()
                self.optimised_colour_angles = np.asarray(result.angles, dtype=np.float64).copy()
                self.optimised_colour_objective = float(result.objective)
                self.optimised_colour_objective_name = variables["objective"].get()
                self.optimised_colour_evaluations = int(result.evaluations)
                self.optimised_colour_iterations = int(result.iterations)
                self.optimised_colour_seconds = float(result.seconds)
                if self.pole_space_var is not None:
                    self.pole_space_combo.configure(state="readonly")
                populate_result_table(result.angles)
                calculate_colours()
                progress["value"] = 100
                angles_text = ", ".join(
                    "{:.3f}".format(value) for value in result.angles
                )
                update_objective_display(result.objective)
                result_var.set(self.tr(
                    "colour.result", angles=angles_text,
                    value=result.objective, seconds=result.seconds
                ))
                self.log(self.tr(
                    "log.colour.result", angles=angles_text,
                    value=result.objective, evaluations=result.evaluations,
                    seconds=result.seconds
                ))
                for button in (btn_poles, btn_density, btn_export):
                    button.configure(state=tk.NORMAL)
            except Exception as exc:
                messagebox.showerror(
                    self.tr("dialog.error_title"), str(exc), parent=dialog
                )

        def projected_poles():
            normals = np.asarray(cloud.normals(), dtype=np.float64)
            x, y, rotated, valid = colour_opt.projected_poles_from_normals(
                normals, state["result"].angles,
                projection=self._canonical_projection()
            )
            rgb = colour_opt.colours_from_projected_poles(
                x, y, variables["space"].get(),
                float(variables["lightness"].get()), valid=valid
            )
            state["rgb"], state["rotated"] = rgb, rotated
            return x[valid], y[valid], rgb[valid]

        def show_rotated_poles():
            if state["result"] is None:
                return
            x, y, rgb = projected_poles()
            old_fig = state.get("poles_fig")
            if old_fig is not None and plt.fignum_exists(old_fig.number):
                plt.close(old_fig)
            fig = plt.figure(figsize=(7, 6))
            state["poles_fig"] = fig
            ax = fig.add_subplot(111)
            stereonet.draw_stereonet(
                ax, projection=self._canonical_projection(), labeled=0
            )
            ax.scatter(
                x, y, s=4, c=rgb.astype(float) / 255.0,
                edgecolors="none", alpha=0.85, zorder=0
            )
            ax.set_title(self.tr("colour.poles_title"))
            fig.tight_layout()
            plt.show(block=False)
            self.log(self.tr("log.colour.poles_shown", count=len(x)))

        def show_rotated_density():
            if state["result"] is None:
                return
            x, y, _ = projected_poles()
            old_fig = state.get("density_fig")
            if old_fig is not None and plt.fignum_exists(old_fig.number):
                plt.close(old_fig)
            grid_size = 2 ** int(self.spin_bins.get())
            X, Y, Z = stereonet.compute_density_grid(
                x, y, grid_res=grid_size, mindensity=1e-3
            )
            fig = plt.figure(figsize=(7, 6))
            state["density_fig"] = fig
            ax = fig.add_subplot(111)
            contour = stereonet.draw_density_from_grid(
                ax, X, Y, Z, projection=self._canonical_projection(),
                labeled=0, filled=(self._canonical_density_style() == "Filled Contours"),
                n_levels=80, principal_poles=None
            )
            if contour is not None:
                fig.colorbar(
                    contour, ax=ax, shrink=0.82,
                    label=self.tr("colour.relative_density")
                )
            ax.set_title(self.tr("colour.density_title"))
            fig.tight_layout()
            plt.show(block=False)
            self.log(self.tr(
                "log.colour.density_shown", count=len(x), grid=grid_size
            ))

        def export_coloured_copy():
            if state["result"] is None:
                return
            try:
                normals, rgb, rotated = calculate_colours()
                points = np.asarray(cloud.points(), dtype=np.float64)
                if len(points) != len(rgb):
                    raise ValueError(self.tr("colour.error.size_mismatch"))
                coloured = pycc.ccPointCloud(
                    points[:, 0], points[:, 1], points[:, 2]
                )
                try:
                    source_name = cloud.getName()
                except Exception:
                    source_name = "Cloud"
                coloured.setName("{} - {} - {}".format(
                    source_name, self.tr("colour.copy_suffix"),
                    variables["space"].get()
                ))
                coloured.setColors(np.ascontiguousarray(rgb, dtype=np.uint8))
                coloured.showColors(True)
                try:
                    coloured.setNormals(
                        np.ascontiguousarray(normals, dtype=np.float32)
                    )
                    coloured.showNormals(False)
                except Exception:
                    pass
                CC = pycc.GetInstance()
                CC.addToDB(coloured)
                CC.updateUI()
                CC.redrawAll()
                self.log(self.tr(
                    "log.colour.copy_created", name=coloured.getName(),
                    count=len(rgb)
                ))
                messagebox.showinfo(
                    self.tr("colour.title"),
                    self.tr("colour.copy_created"), parent=dialog
                )
            except Exception as exc:
                messagebox.showerror(
                    self.tr("dialog.error_title"), str(exc), parent=dialog
                )

        def make_action_button(icon_name, command, tooltip_key, fallback,
                               initially_enabled=True):
            button = tk.Button(
                buttons, command=command, width=58, height=54,
                padx=3, pady=3,
                state=tk.NORMAL if initially_enabled else tk.DISABLED
            )
            icon = self.icons.get(icon_name) if getattr(self, "icons", None) else None
            if icon is not None:
                button.configure(image=icon, text="", compound=tk.CENTER)
                button._dse_icon_image = icon
            else:
                button.configure(text=fallback, wraplength=52)
            self.add_tooltip(button, tooltip_key)
            button.pack(side=tk.LEFT, padx=5)
            return button

        btn_optimise = make_action_button(
            "imagen_rotacion", optimise, "tip.colour.optimise",
            self.tr("colour.optimise"), True
        )
        btn_poles = make_action_button(
            "plot_poles", show_rotated_poles, "tip.colour.show_poles",
            self.tr("colour.show_poles"), False
        )
        btn_density = make_action_button(
            "principal_poles", show_rotated_density,
            "tip.colour.show_density",
            self.tr("colour.show_density"), False
        )
        btn_export = make_action_button(
            "imagen_HSV_icono", export_coloured_copy, "tip.colour.export_copy",
            self.tr("colour.export_copy"), False
        )

        # If an optimisation already exists, reopen this dialog as completed.
        if self.optimised_colour_angles is not None:
            existing_angles = np.asarray(self.optimised_colour_angles, dtype=float).copy()
            state["result"] = colour_opt.OptimisationResult(
                angles=existing_angles,
                rotation=np.asarray(self.optimised_colour_rotation, dtype=np.float64).copy(),
                objective=float(self.optimised_colour_objective) if self.optimised_colour_objective is not None else 0.0,
                equivalent_degrees=float("nan"),
                evaluations=int(self.optimised_colour_evaluations or 0),
                iterations=int(self.optimised_colour_iterations or 0),
                seconds=float(self.optimised_colour_seconds or 0.0),
                success=True, message=""
            )
            populate_result_table(existing_angles)
            calculate_colours()
            progress["value"] = 100
            angles_text = ", ".join("{:.3f}".format(value) for value in existing_angles)
            update_objective_display(float(self.optimised_colour_objective or 0.0))
            result_var.set(self.tr(
                "colour.result", angles=angles_text,
                value=float(self.optimised_colour_objective or 0.0),
                seconds=float(self.optimised_colour_seconds or 0.0)
            ))
            for button in (btn_poles, btn_density, btn_export):
                button.configure(state=tk.NORMAL)

        ttk.Button(
            buttons, text=self.tx("Close"), command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5, ipadx=12, ipady=4)

        self._install_context_help_recursive(dialog)
        dialog.update_idletasks()
        width = max(740, dialog.winfo_reqwidth())
        height = max(560, dialog.winfo_reqheight())
        dialog.geometry("{}x{}".format(width, height))

    def open_normal_spacing_tool(self):
        cloud = self._analysis_cloud()
        if cloud is None: return
        families = self._tool_families(cloud)
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tx(self.tr("gui.normal_spacing")))
        dialog.after_idle(lambda w=dialog: self._translate_widget_tree(w))
        dialog.geometry("470x300")
        dialog.grab_set()

        all_value = self.tx("All")
        family = tk.StringVar(value=all_value)
        bandwidth = tk.StringVar(value="0")
        minimum = tk.StringVar(value="0.01")
        tolerance = tk.StringVar(value="0.00001")
        export = tk.IntVar(value=0)

        controls = []
        for row, (label, var, values, tip_key) in enumerate([
            (self.tx("Family"), family, [all_value] + families, "gui.spacing_family"),
            (self.tx("Bandwidth (0=auto)"), bandwidth, None, "gui.spacing_bandwidth"),
            (self.tx("Minimum spacing"), minimum, None, "gui.spacing_minimum"),
            (self.tx("D tolerance"), tolerance, None, "gui.spacing_dtolerance")
        ]):
            tk.Label(dialog, text=label).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
            widget = ttk.Combobox(dialog, textvariable=var, values=values, state="readonly", width=22) if values else tk.Entry(dialog, textvariable=var, width=25)
            widget.grid(row=row, column=1, padx=12, pady=7)
            self.add_tooltip(widget, tip_key)
            controls.append(widget)

        export_widget = tk.Checkbutton(dialog, text=self.tx(self.tr("gui.export_results")), variable=export)
        export_widget.grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=12, pady=8)
        self.add_tooltip(export_widget, "gui.spacing_export")
        dialog.after_idle(lambda: self._install_context_help_recursive(dialog))

        def calculate():
            progress_dialog = None
            try:
                selected = (
                    families if family.get() == all_value
                    else [int(family.get())]
                )
                progress_dialog = DSEProgressDialog(
                    self.root, title=self.tx("Normal Spacing Progress")
                )
                results = []
                family_count = len(selected)
                for family_position, family_id in enumerate(selected):
                    family_start = 100.0 * family_position / family_count
                    family_span = 100.0 / family_count

                    def spacing_progress(percent, status_text):
                        overall = family_start + family_span * percent / 100.0
                        text = (
                            f"DS {family_id} ({family_position + 1}/"
                            f"{family_count}): {status_text}"
                        )
                        return progress_dialog.update_progress(overall, text)

                try:
                    result = stereonet.analyze_normal_spacing(
                        cloud, family_id, float(bandwidth.get()),
                        float(minimum.get()), float(tolerance.get()),
                        progress_callback=spacing_progress
                    )
                    results.append(result)
                except ValueError as exc:
                    if str(exc) == self.tr("error.two_planes_required"):
                        continue
                    raise
                progress_dialog.update_progress(100, self.tx(self.tr("gui.normal_spacing_completed")))
                folder = None
                if export.get():
                    folder = filedialog.askdirectory(parent=dialog)
                    if not folder:
                        return
                    for result in results:
                        self._save_spacing_result(result, folder)
                spacing_rows = []
                for result in results:
                    group_map = {g["plane_id"]: g for g in result["groups"]}
                    for relationship, array in (("nearest", result["nonpersistent_raw"]), ("consecutive", result["full_persistent_raw"])):
                        for record in array:
                            source = group_map.get(int(record[1]), {})
                            target = group_map.get(int(record[2]), {})
                            spacing_rows.append((
                                int(record[0]), relationship,
                                ",".join(map(str, source.get("cluster_ids", ()))),
                                ",".join(map(str, target.get("cluster_ids", ()))),
                                int(record[1]), int(record[2]),
                                f"{record[3]:.8g}", f"{record[4]:.8g}", f"{record[5]:.8g}"
                            ))
                spacing_columns = (
                    self.tx("DS"), self.tx("Relation"),
                    self.tx(self.tr("gui.source_clusters")),
                    self.tx(self.tr("gui.related_clusters")),
                    self.tx(self.tr("gui.source_plane")),
                    self.tx(self.tr("gui.related_plane")),
                    self.tx("Spacing"), self.tx(self.tr("gui.d_source")),
                    self.tx(self.tr("gui.d_related"))
                )

                def save_spacing_txt():
                    path = filedialog.asksaveasfilename(
                        parent=dialog, title=self.tr("gui.save_results"),
                        defaultextension=".txt",
                        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                        initialfile="normal-spacing-results.txt"
                    )
                    if not path:
                        return
                    try:
                        with open(path, "w", encoding="utf-8") as stream:
                            stream.write("\t".join(spacing_columns) + "\n")
                            for row in spacing_rows:
                                stream.write("\t".join(str(value) for value in row) + "\n")
                        self.log(self.tr("gui.normal_spacing_results_saved"))
                    except Exception as exc:
                        messagebox.showerror(
                            self.tr("gui.normal_spacing"),
                            self.tr("gui.normal_spacing_save_error", error=exc),
                            parent=dialog
                        )

                self._show_result_table(
                    self.tx("Normal Spacing Results"), spacing_columns,
                    spacing_rows, save_callback=save_spacing_txt
                )
                window_title = self.tx("Normal Spacing by Family")
                figure, axes = self._create_analysis_figure(
                    len(results), window_title
                )
                for axis, result in zip(axes, results):
                    axis.plot(
                        result["x_nonpersistent"],
                        result["kde_nonpersistent"], "b--",
                        linewidth=1.4, label=self.tx("Non-persistent")
                    )
                    axis.plot(
                        result["x_full"], result["kde_full"], "g-",
                        linewidth=1.4, label=self.tx("Full persistent")
                    )
                    axis.set_title(
                        f"DS {result['family_id']}\n"
                        f"S1={result['mean']:.4g}; "
                        f"S2={result['mean_full']:.4g}",
                        pad=8
                    )
                    axis.set_xlabel(self.tx(self.tr("gui.spacing")))
                    axis.set_ylabel(self.tx("Density"))
                    axis.legend(loc="best", fontsize=8, framealpha=0.9)
                    self._format_analysis_axis(axis)
                    self.log(
                        self.tr("log.spacing_summary", family=result["family_id"], mean=f"{result['mean']:.4g}", std=f"{result['std']:.4g}")
                    )
                if folder:
                    figure.savefig(
                        os.path.join(folder, "normal-spacing.png"),
                        dpi=200, bbox_inches="tight"
                    )
                    figure.savefig(
                        os.path.join(folder, "normal-spacing.pdf"),
                        bbox_inches="tight"
                    )
                figure.show()
                plt.show(block=False)
                dialog.destroy()
            except stereonet.CalculationCancelledException:
                self.log(self.tr("log.spacing_cancelled"))
            except Exception as exc:
                messagebox.showerror(self.tx(self.tr("gui.normal_spacing")), str(exc))
            finally:
                if progress_dialog is not None:
                    progress_dialog.close()

        tk.Button(dialog, text=self.tx("Calculate"), command=calculate, bg="#d1e7dd", width=24).grid(row=5, column=0, columnspan=2, pady=15)

    def open_persistence_tool(self):
        cloud = self._analysis_cloud()
        if cloud is None: return
        families = self._tool_families(cloud)
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tx(self.tr("gui.persistence")))
        dialog.geometry("430x190")
        dialog.after_idle(lambda w=dialog: self._translate_widget_tree(w))
        dialog.grab_set()

        all_value = self.tx("All")
        family = tk.StringVar(value=all_value)
        export = tk.IntVar(value=0)
        tolerance = tk.StringVar(value="0.00001")

        tk.Label(dialog, text=self.tx("Family")).grid(row=0, column=0, padx=12, pady=10)
        family_widget = ttk.Combobox(dialog, textvariable=family, values=[all_value] + families, state="readonly", width=22)
        family_widget.grid(row=0, column=1, padx=12, pady=10)
        self.add_tooltip(family_widget, "gui.persistence_family")
        tk.Label(dialog, text=self.tx("D tolerance")).grid(row=1, column=0, padx=12, pady=8)
        tolerance_widget = tk.Entry(dialog, textvariable=tolerance, width=25)
        tolerance_widget.grid(row=1, column=1, padx=12, pady=8)
        self.add_tooltip(tolerance_widget, "gui.persistence_dtolerance")
        export_widget = tk.Checkbutton(dialog, text=self.tx(self.tr("gui.export_results")), variable=export)
        export_widget.grid(row=2, column=0, columnspan=2, padx=12, pady=8)
        self.add_tooltip(export_widget, "gui.persistence_export")
        dialog.after_idle(lambda: self._install_context_help_recursive(dialog))

        def calculate():
            progress_dialog = None
            try:
                progress_dialog = DSEProgressDialog(
                    self.root,
                    title=self.tx("Persistence Progress")
                )

                def persistence_progress(percent, status_text):
                    return progress_dialog.update_progress(
                        percent, status_text
                    )

                rows, summaries = stereonet.analyze_persistence(
                    cloud, float(tolerance.get()),
                    progress_callback=persistence_progress
                )
                if family.get() != all_value:
                    fid = int(family.get())
                    rows = [r for r in rows if r["family_id"] == fid]
                    summaries = [r for r in summaries if r["family_id"] == fid]
                if not rows: raise ValueError(self.tr("gui.no_valid_persistence"))
                folder = filedialog.askdirectory(parent=dialog) if export.get() else None
                if export.get() and not folder: return
                if folder:
                    with open(os.path.join(folder, "persistence-report.txt"), "w", encoding="ascii") as stream:
                        stream.write("\t".join([self.tx("DS"), self.tx("Plane"), self.tx("Clusters"), self.tx("D"), self.tx("Points"), self.tx("P_dip"), self.tx("P_strike"), self.tx("P_max"), self.tx("Area")]) + "\n")
                        for r in rows:
                            stream.write(f"{r['family_id']}\t{r['plane_id']}\t{','.join(map(str, r['cluster_ids']))}\t{r['D']:.8g}\t{r['n_points']}\t{r['p_dip']:.8g}\t{r['p_strike']:.8g}\t{r['p_max']:.8g}\t{r['area']:.8g}\n")
                ids = sorted({row["family_id"] for row in rows})
                window_title = self.tx("Persistence by Family")
                figure, axes = self._create_analysis_figure(
                    len(ids), window_title
                )
                for axis, family_id in zip(axes, ids):
                    values = [
                        row["p_max"] for row in rows
                        if row["family_id"] == family_id
                    ]
                    axis.hist(
                        values, bins="auto", color="#4c78a8",
                        edgecolor="white", linewidth=0.8
                    )
                    mean_value = float(np.mean(values))
                    axis.set_title(
                        self.tr("gui.persistence_plot_title", family=family_id, count=len(values), mean=f"{mean_value:.3g}"),
                        pad=8
                    )
                    axis.set_xlabel(self.tx(self.tr("gui.persistence_m")))
                    axis.set_ylabel(self.tx("Planes"))
                    self._format_analysis_axis(axis)
                if folder:
                    figure.savefig(
                        os.path.join(folder, "persistence-histograms.png"),
                        dpi=200, bbox_inches="tight"
                    )
                    figure.savefig(
                        os.path.join(folder, "persistence-histograms.pdf"),
                        bbox_inches="tight"
                    )
                figure.show()
                plt.show(block=False)
                self.log(
                    self.tr("log.persistence_summary", count=len(rows))
                )
                dialog.destroy()
            except stereonet.CalculationCancelledException:
                self.log(self.tr("log.persistence_cancelled"))
            except Exception as exc:
                messagebox.showerror(self.tx(self.tr("gui.persistence")), str(exc))
            finally:
                if progress_dialog is not None:
                    progress_dialog.close()

        tk.Button(dialog, text=self.tx("Calculate"), command=calculate, bg="#d1e7dd", width=24).grid(row=3, column=0, columnspan=2, pady=14)

    def get_selected_cloud(self, verbose=True):
        CC = pycc.GetInstance()
        entities = CC.getSelectedEntities()

        if len(entities) == 0:
            if verbose:
                self.log(self.tr("log.workflow_no_cloud"))
            return None

        cloud = entities[0]
        return cloud

    def refresh_selected_cloud(self):
        """Reload the selected CloudCompare entity and update the workflow."""
        cloud = self.get_selected_cloud(verbose=False)
        if cloud is None:
            self.log(self.tr("log.refresh_no_cloud"))
        else:
            self.log(self.tr("log.refresh_selected", name=cloud.getName()))
        try:
            cc = pycc.GetInstance()
            cc.updateUI()
            cc.redrawAll()
        except Exception as exc:
            self.log(self.tr("log.refresh_warning", exc=exc))
        # CloudCompare updates its selection/UI state asynchronously.
        # Evaluate the workflow only after the refresh request has been sent.
        self.check_cloud_and_update_workflow()
        self.root.after_idle(self._initial_workflow_check)
        self.root.after(150, self._initial_workflow_check)

    def check_cloud_and_update_workflow(self):
        """Inspects active point cloud state and enforces smart workflow dependencies."""
        cloud = self.get_selected_cloud(verbose=False)

        if cloud is None:
            self.lbl_cloud_status.config(text=self.tx("Status: No Cloud Selected"), fg="#dc3545")
            self._set_step1_state(False)
            self._set_step2_state(False)
            self._set_step3_state(False)
            self.tools_menu.entryconfig(0, state=tk.DISABLED)
            self.tools_menu.entryconfig(2, state=tk.DISABLED)
            self.tools_menu.entryconfig(3, state=tk.DISABLED)
            return False

        cloud_name = cloud.getName()
        has_normals = cloud.hasNormals()
        has_js_field = (cloud.getScalarFieldIndexByName("Discontinuity Set (DS)") >= 0)
        has_cl_field = (cloud.getScalarFieldIndexByName("Cluster id (cl)") >= 0)
        has_current_js = has_js_field and self._js_is_current()
        has_cluster_analysis = bool(self.cluster_planes_results)

        # Normal Spacing and Persistence require cluster analysis to be completed AND cloud to have DS and cl fields
        cluster_tools_state = tk.NORMAL if (has_js_field and has_cl_field and has_cluster_analysis) else tk.DISABLED

        self.tools_menu.entryconfig(0, state=tk.NORMAL if has_normals else tk.DISABLED)
        self.tools_menu.entryconfig(2, state=cluster_tools_state)
        self.tools_menu.entryconfig(3, state=cluster_tools_state)

        has_principal_poles = (len(self.principal_poles) > 0)

        # Step 1: Stereonet & Density -> Needs computed normals
        self._set_step1_state(has_normals)

        # Step 2: JS Classification -> Needs normals AND active Principal Poles
        self._set_step2_state(has_normals and has_principal_poles)

        # "Plot Poles by Family" -> Needs the 'JS' Scalar Field already computed
        self.btn_poles_by_family.config(state=tk.NORMAL if has_current_js else tk.DISABLED)

        # Step 3: Spatial Clustering -> Needs ONLY the 'JS' Scalar Field on the cloud
        self._set_step3_state(has_current_js)

        # Facets require a successful cluster analysis in the current session.
        required_analysis_fields = ("Discontinuity Set (DS)", "Cluster id (cl)", "A", "B", "C", "D")
        has_analysis_data = all(
            cloud.getScalarFieldIndexByName(name) >= 0
            for name in required_analysis_fields
        )
        facets_ready = (
            has_current_js
            and has_analysis_data
            and has_cluster_analysis
        )
        self.btn_facets.config(
            state=tk.NORMAL if facets_ready else tk.DISABLED
        )

        # Dynamic Status Feedback Text
        status_info = []
        if has_normals:
            status_info.append(self.tx("Normals OK"))
        else:
            status_info.append(self.tx("Missing Normals"))

        if has_current_js:
            status_info.append(self.tx("DS Current (Clustering Ready)"))
        elif has_js_field:
            status_info.append(self.tx("DS Outdated - Reclassify"))

        self.lbl_cloud_status.config(
            text=f"'{cloud_name}': " + " | ".join(status_info),
            fg="#198754" if (has_normals or has_js_field) else "#dc3545"
        )

        return True

    def _set_workflow_tab_state(self, tab, enabled):
        if not hasattr(self, "workflow_notebook"):
            return
        self.workflow_notebook.tab(
            tab, state="normal" if enabled else "disabled"
        )

    def _set_step1_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_poles.config(state=state)
        self.btn_density.config(state=state)
        density_ready = enabled and self.cached_X is not None
        self.btn_show_density.config(
            state=tk.NORMAL if density_ready else tk.DISABLED
        )
        if hasattr(self, "btn_generate_colour_cloud"):
            self.btn_generate_colour_cloud.config(
                state=tk.NORMAL if enabled else tk.DISABLED
            )
        if hasattr(self, "pole_space_combo"):
            self.pole_space_combo.configure(
                state="readonly" if enabled else "disabled"
            )
        self._set_workflow_tab_state(self.step1_tab, enabled)

    def _set_step2_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_classify_js.config(state=state)
        self._set_workflow_tab_state(self.step2_tab, enabled)

    def _set_step3_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_clusterize.config(state=state)
        self._set_workflow_tab_state(self.step3_tab, enabled)

    def _use_rotated_pole_space(self):
        return (
            self.optimised_colour_rotation is not None
            and self.pole_space_var is not None
            and self._canonical_pole_space() == "rotated"
        )

    def _project_cloud_poles_for_step1(self, cloud, projection):
        if not self._use_rotated_pole_space():
            return stereonet.project_poles(cloud, projection=projection)
        normals = np.asarray(cloud.normals(), dtype=np.float64)
        x, y, _, valid = colour_opt.projected_poles_from_normals(
            normals, self._rotation_angles_from_matrix(), projection=projection
        )
        return x[valid], y[valid]

    def _rotation_angles_from_matrix(self):
        """Return a lightweight proxy consumed by colour_opt through cached R."""
        # projected_poles_from_normals is angle based, so use direct helper below instead.
        return np.zeros(3)

    def _rotated_projected_poles(self, cloud, projection):
        normals = np.asarray(cloud.normals(), dtype=np.float64)
        lengths = np.linalg.norm(normals, axis=1)
        valid = np.isfinite(normals).all(axis=1) & (lengths > np.finfo(float).eps)
        unit = normals[valid] / lengths[valid, None]
        rotated = (self.optimised_colour_rotation @ unit.T).T
        rotated[rotated[:, 2] < 0.0] *= -1.0
        dipdir, dip = stereonet.f_vnorm2clar_v02(rotated)
        return stereonet.f_clar2cart(dipdir, dip, projection=projection)

    def _poles_from_rotated_to_original(self, poles, projection):
        """Convert rotated KDE peaks to real orientations for DS classification."""
        if not self._use_rotated_pole_space():
            return poles

        converted = []
        inverse_rotation = self.optimised_colour_rotation.T

        for index, rotated_pole in enumerate(poles, start=1):
            rotated_normal = stereonet.f_pole2vnor_v02(
                np.array(
                    [[rotated_pole["x"], rotated_pole["y"]]],
                    dtype=float
                ),
                projection=projection,
            )[0]

            original_normal = inverse_rotation @ rotated_normal
            original_normal /= np.linalg.norm(original_normal)

            if original_normal[2] < 0.0:
                original_normal *= -1.0

            dipdir, dip = stereonet.f_vnorm2clar_v02(
                original_normal.reshape(1, 3)
            )

            pole = stereonet.create_pole_dict(
                float(dipdir[0]),
                float(dip[0]),
                projection=projection,
                idx=index,
            )
            pole["density"] = float(rotated_pole.get("density", 0.0))

            # Position of the KDE maximum in the rotated stereonet.
            pole["display_x"] = float(rotated_pole["x"])
            pole["display_y"] = float(rotated_pole["y"])
            pole["display_normal"] = rotated_normal.copy()
            pole["normal"] = original_normal.copy()

            converted.append(pole)

        return converted

    def _rebuild_display_principal_poles(self, space=None):
        """Project the real pole table into the requested density space."""
        projection = self.cached_projection or self._canonical_projection()
        space = space or self.cached_pole_space
        if space != "rotated":
            display_poles = []
            for pole in self.principal_poles:
                x, y = stereonet.f_clar2cart(
                    pole["dipdir"], pole["dip"], projection=projection
                )
                display_poles.append({
                    "id": pole["id"],
                    "idx": pole["idx"],
                    "x": float(np.atleast_1d(x)[0]),
                    "y": float(np.atleast_1d(y)[0]),
                    "density": float(pole.get("density", 0.0)),
                })
            self.display_principal_poles = display_poles
            return

        rotation = self.optimised_colour_rotation
        if rotation is None:
            self.display_principal_poles = []
            return

        display_poles = []
        for pole in self.principal_poles:
            original_normal = np.asarray(pole["normal"], dtype=float)
            rotated_normal = rotation @ original_normal
            if rotated_normal[2] < 0.0:
                rotated_normal *= -1.0
            dipdir, dip = stereonet.f_vnorm2clar_v02(
                rotated_normal.reshape(1, 3)
            )
            x, y = stereonet.f_clar2cart(
                dipdir, dip, projection=projection
            )
            display_poles.append({
                "id": pole["id"],
                "idx": pole["idx"],
                "x": float(np.atleast_1d(x)[0]),
                "y": float(np.atleast_1d(y)[0]),
                "density": float(pole.get("density", 0.0)),
            })
        self.display_principal_poles = display_poles

    def _update_pairwise_angles(self):
        if not hasattr(self, "pairwise_tree"):
            return
        poles = self.principal_poles
        for item in self.pairwise_tree.get_children():
            self.pairwise_tree.delete(item)
        if not poles:
            self.notebook.tab(self.tab_pairwise, state="disabled")
            return
        ids = ["J_{}".format(i) for i in range(1, len(poles) + 1)]
        columns = ["row"] + ids
        self.pairwise_tree.configure(columns=columns, show="headings")
        self.pairwise_tree.heading("row", text=self.tr("pairwise.family"))
        self.pairwise_tree.column("row", width=80, minwidth=70, anchor=tk.CENTER)
        normals = []
        for pole in poles:
            x, y = stereonet.f_clar2cart(pole["dipdir"], pole["dip"], projection="Equal-angle")
            normals.append(stereonet.f_pole2vnor_v02(np.array([[float(x), float(y)]]), projection="Equal-angle")[0])
        normals = np.asarray(normals, dtype=float)
        dots = np.clip(np.abs(normals @ normals.T), 0.0, 1.0)
        angles = np.degrees(np.arccos(dots))
        for column in ids:
            self.pairwise_tree.heading(column, text=column)
            self.pairwise_tree.column(column, width=85, minwidth=70, anchor=tk.CENTER)
        for i, family in enumerate(ids):
            values = [family] + ["{:.2f}".format(v) for v in angles[i]]
            self.pairwise_tree.insert("", tk.END, values=values)
        self.notebook.tab(self.tab_pairwise, state="normal")

    # ---------------------------------------------------------
    # STEP 1 EXECUTIONS
    # ---------------------------------------------------------
    def generate_principal_colour_cloud(self):
        """Create a CloudCompare copy coloured from the selected pole space."""
        cloud = self.get_selected_cloud()
        if cloud is None or not cloud.hasNormals():
            messagebox.showwarning(
                self.tr("dialog.warning_title"),
                self.tr("gui.export_hsv_requires_normals")
            )
            return

        try:
            projection = self._canonical_projection()
            selected_space = self._canonical_pole_space()
            colour_space = self.principal_colour_space_var.get()
            lightness = float(self.principal_colour_lightness_var.get())
            if not 0.0 <= lightness <= 100.0:
                raise ValueError(self.tr("colour.error.lightness_range"))

            points = np.asarray(cloud.points(), dtype=np.float64)
            normals = np.asarray(cloud.normals(), dtype=np.float64)
            if len(points) != len(normals):
                raise ValueError(self.tr("colour.error.size_mismatch"))

            if selected_space == "rotated":
                if self.optimised_colour_rotation is None:
                    raise ValueError(self.tr("gui.export_hsv_no_rotation"))
                lengths = np.linalg.norm(normals, axis=1)
                valid = np.isfinite(normals).all(axis=1) & (
                    lengths > np.finfo(float).eps
                )
                unit = np.zeros_like(normals)
                unit[valid] = normals[valid] / lengths[valid, None]
                rotated = np.zeros_like(unit)
                rotated[valid] = (self.optimised_colour_rotation @ unit[valid].T).T
                rotated_valid = rotated[valid]
                rotated_valid[rotated_valid[:, 2] < 0.0] *= -1.0
                dipdir, dip = stereonet.f_vnorm2clar_v02(rotated_valid)
                x, y = stereonet.f_clar2cart(
                    dipdir, dip, projection=projection
                )
                rgb_valid = colour_opt.colours_from_projected_poles(
                    x, y, colour_space=colour_space, lightness=lightness
                )
                rgb = np.full((len(normals), 3), 128, dtype=np.uint8)
                rgb[valid] = rgb_valid
            else:
                x, y = stereonet.project_poles(cloud, projection=projection)
                rgb = colour_opt.colours_from_projected_poles(
                    x, y, colour_space=colour_space, lightness=lightness
                )
                if len(rgb) != len(points):
                    raise ValueError(self.tr("colour.error.size_mismatch"))

            coloured = pycc.ccPointCloud(
                points[:, 0], points[:, 1], points[:, 2]
            )
            try:
                source_name = cloud.getName()
            except Exception:
                source_name = "Cloud"
            coloured.setName(
                "{} - {} - {} - {}".format(
                    source_name, self.tr("colour.copy_suffix"),
                    colour_space, selected_space.capitalize()
                )
            )
            coloured.setColors(np.ascontiguousarray(rgb, dtype=np.uint8))
            coloured.showColors(True)
            try:
                coloured.setNormals(
                    np.ascontiguousarray(normals, dtype=np.float32)
                )
                coloured.showNormals(False)
            except Exception:
                pass

            CC = pycc.GetInstance()
            CC.addToDB(coloured)
            CC.updateUI()
            CC.redrawAll()
            self.log(self.tr(
                "log.hsv_export_created", name=coloured.getName(),
                count=len(points), space="{} / {}".format(colour_space, selected_space)
            ))
            messagebox.showinfo(
                self.tr("colour.title"),
                self.tr("gui.export_hsv_done"), parent=self.root
            )
        except Exception as exc:
            self.log(self.tr("log.hsv_export_error", error=exc))
            messagebox.showerror(
                self.tr("dialog.error_title"), str(exc), parent=self.root
            )


    def run_plot_poles(self):
        cloud = self.get_selected_cloud()
        if cloud is None or not cloud.hasNormals():
            messagebox.showwarning(self.tx("Warning"), self.tx("Select a cloud with computed normals."))
            return

        projection = self._canonical_projection()
        rotated_space = self._use_rotated_pole_space()
        labeled = 0 if rotated_space else self.labeled_var.get()

        self.log(self.tr("log.extracting_normals_projection", projection=projection))
        stage_start = time.perf_counter()
        xp, yp = (self._rotated_projected_poles(cloud, projection) if self._use_rotated_pole_space() else stereonet.project_poles(cloud, projection=projection))
        self.log(self.tr("log.timing_pole_projection", seconds=time.perf_counter() - stage_start))

        fig, ax = plt.subplots(figsize=(7, 7))
        stereonet.draw_stereonet(ax, projection=projection, labeled=labeled)

        def poles_format_coord(x_pos, y_pos):
            dipdir, dip = stereonet.f_cart2clar(x_pos, y_pos, projection=projection)
            if dipdir is None:
                return self.tr("plot.outside", radius=np.sqrt(x_pos**2 + y_pos**2))
            return self.tr("plot.coord", dipdir=dipdir, dip=dip, projection=projection)

        ax.format_coord = poles_format_coord
        ax.plot(xp, yp, "b.", markersize=1.0, alpha=0.4, zorder=0)
        space_name = self.tx("Rotated space") if rotated_space else self.tx("Original space")
        plt.title(
            self.tr("plot.poles_title_full", count=len(xp), projection=projection, space=space_name)
        )
        self.log(self.tr("log.plotted_poles", count=len(xp)))
        plt.show()

    def run_show_density(self):
        if not self.cached_density_grids:
            messagebox.showwarning(
                self.tx("Density"),
                self.tr("dialog.calc_density_first")
            )
            return
        self.refresh_plot()
        self.log(
            self.tr("log.displayed_cached_density")
        )

    def run_plot_density(self):
        cloud = self.get_selected_cloud()
        if cloud is None or not cloud.hasNormals():
            messagebox.showwarning(self.tx("Warning"), self.tx("Select a cloud with computed normals."))
            return

        projection = self._canonical_projection()
        bins_level = int(self.spin_bins.get())
        grid_res = 2**bins_level
        min_angle = float(self.spin_angle.get())
        max_poles = int(self.spin_maxpoles.get())

        operation_start = time.perf_counter()
        self.log(self.tr("log.step1_header"))
        self.log(self.tr("log.grid_resolution", res=grid_res, level=bins_level))
        
        selected_space = (
            "rotated" if self._use_rotated_pole_space() else "original"
        )
        original_xp, original_yp = stereonet.project_poles(
            cloud, projection=projection
        )
        pole_coordinates = {"original": (original_xp, original_yp)}
        if self.optimised_colour_rotation is not None:
            pole_coordinates["rotated"] = self._rotated_projected_poles(
                cloud, projection
            )
        xp, yp = pole_coordinates[selected_space]
        if len(xp) == 0:
            self.log(self.tr("log.error_no_poles"))
            return

        self.log(self.tr("log.computing_density", count=len(xp)))
        stage_start = time.perf_counter()
        density_grids = {}
        for space, (space_xp, space_yp) in pole_coordinates.items():
            density_grids[space] = stereonet.compute_density_grid(
                space_xp, space_yp, grid_res=grid_res, mindensity=1e-3
            )
        X, Y, Z = density_grids[selected_space]
        self.log(self.tr("log.timing_density", seconds=time.perf_counter() - stage_start))

        self.log(self.tr("log.detecting_peaks", angle=min_angle))
        stage_start = time.perf_counter()
        principal_poles = stereonet.find_principal_poles(
            X, Y, Z, 
            projection=projection, 
            min_angle_deg=min_angle, 
            max_poles=max_poles
        )
        self.log(self.tr("log.timing_pole_search", seconds=time.perf_counter() - stage_start))

        self.cached_X = X
        self.cached_Y = Y
        self.cached_Z = Z
        self.cached_xp = xp
        self.cached_yp = yp
        self.cached_projection = projection
        self.cached_density_grids = density_grids
        self.cached_pole_space = selected_space
        self.principal_poles = self._poles_from_rotated_to_original(
            principal_poles, projection
        )
        self._rebuild_display_principal_poles(selected_space)
        self.poles_revision += 1
        self.js_revision = -1
        self.cluster_planes_results = None
        self._set_poles_status("automatic")

        try:
            cone_thresh = float(self.spin_js_cone.get())
            stage_start = time.perf_counter()
            fisher = stereonet.compute_cloud_fisher_k(
                cloud, self.principal_poles,
                max_cone_angle_deg=cone_thresh
            )
            self._apply_fisher_results(fisher, provisional=True)
            self.log(self.tr("log.timing_provisional_fisher", seconds=time.perf_counter() - stage_start))
        except Exception as exc:
            self.log(self.tr("log.fisher_provisional_warning", exc=exc))

        self.log(self.tr("log.extracted_poles", count=len(principal_poles)))
        self.update_table_view()
        self.refresh_plot()

        # Step 1 complete: unlock and show DS classification.
        self.check_cloud_and_update_workflow()
        if self.principal_poles:
            self.workflow_notebook.select(self.step2_tab)
        self.log(self.tr("log.timing_step1_total", seconds=time.perf_counter() - operation_start))

    # ---------------------------------------------------------
    # STEP 2 EXECUTIONS
    # ---------------------------------------------------------
    def run_classify_js(self):
        cloud = self.get_selected_cloud()
        if cloud is None:
            return

        if not self.principal_poles or len(self.principal_poles) == 0:
            messagebox.showwarning(self.tx("Workflow Error"), self.tx("Step 1 incomplete: No principal poles extracted."))
            return

        try:
            cone_thresh = float(self.spin_js_cone.get())
        except ValueError:
            messagebox.showerror(self.tx("Error"), self.tx("Please enter a valid numeric value for DS Cone Threshold."))
            return

        operation_start = time.perf_counter()
        self.log(self.tr("log.step2_header", cone=cone_thresh))
        self.log(self.tr("log.scalar_writer_backend"))

        progress_dialog = DSEProgressDialog(self.root, title=self.tx("DS Family Classification Progress"))

        def progress_callback(percent, status_text):
            self.log(f"  [JS] {self.tx(status_text)}")
            return progress_dialog.update_progress(percent, status_text)

        try:
            stage_start = time.perf_counter()
            stats, msg = stereonet.classify_point_cloud_js(
                cloud, self.principal_poles, max_cone_angle_deg=cone_thresh,
                progress_callback=progress_callback
            )
            classification_seconds = time.perf_counter() - stage_start
        finally:
            progress_dialog.close()

        if stats is None:
            if "cancelled" in msg.lower():
                self.log(self.tr("log.classify_cancelled"))
                messagebox.showinfo(self.tx("Cancelled"), self.tx("Process cancelled by user."))
            else:
                messagebox.showerror(self.tx("Error"), self.tx(msg))
                self.log(self.tx(msg))
            return

        self.js_revision = self.poles_revision
        self.cluster_planes_results = None
        self.log(self.tr("log.ds_field_created"))
        self.log(self.tr("log.timing_ds_classification", seconds=classification_seconds))
        
        total_pts = cloud.size()
        for set_idx in sorted(stats.keys()):
            cnt = stats[set_idx]
            pct = (cnt / total_pts) * 100.0
            if set_idx == 0:
                self.log(self.tr("log.ds_unclassified_stats", count=cnt, pct=f"{pct:.2f}"))
            else:
                self.log(self.tr("log.ds_family_stats", set_idx=set_idx, count=cnt, pct=f"{pct:.2f}"))

        try:
            js_idx = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
            js_values = np.asarray(
                cloud.getScalarField(js_idx).asArray(), dtype=int
            )
            stage_start = time.perf_counter()
            fisher = stereonet.compute_cloud_fisher_k(
                cloud, self.principal_poles, family_ids=js_values
            )
            self._apply_fisher_results(fisher, provisional=False)
            self.log(self.tr("log.timing_final_fisher", seconds=time.perf_counter() - stage_start))
            self.update_table_view()
        except Exception as exc:
            self.log(self.tr("log.fisher_final_warning", exc=exc))

        pycc.GetInstance().redrawAll()

        # Refresh an existing family plot with the new JS classification.
        self._refresh_family_plot_if_open(reload_data=True)

        # Step 2 complete: unlock and show Spatial clustering.
        self.check_cloud_and_update_workflow()
        if self._js_is_current():
            self.workflow_notebook.select(self.step3_tab)
        self.log(self.tr("log.timing_step2_total", seconds=time.perf_counter() - operation_start))

    def _refresh_family_plot_if_open(self, reload_data=False):
        if self.family_fig is None:
            return
        if not plt.fignum_exists(self.family_fig.number):
            self.family_fig = None
            self.family_ax = None
            self.family_plot_data = None
            return

        cloud = self.get_selected_cloud(verbose=False)
        if cloud is None:
            return

        projection = self._canonical_projection()
        labeled = self.labeled_var.get()

        if reload_data or self.family_plot_data is None:
            if cloud.getScalarFieldIndexByName("Discontinuity Set (DS)") < 0:
                return
            xp, yp, fam = stereonet.project_poles_by_family(
                cloud, projection=projection
            )
            self.family_plot_data = (xp, yp, fam, projection)
        else:
            xp, yp, fam, cached_projection = self.family_plot_data
            if cached_projection != projection:
                xp, yp, fam = stereonet.project_poles_by_family(
                    cloud, projection=projection
                )
                self.family_plot_data = (xp, yp, fam, projection)

        ax = self.family_ax
        ax.clear()
        stereonet.draw_stereonet(
            ax, projection=projection, labeled=labeled
        )

        def poles_format_coord(x_pos, y_pos):
            dipdir, dip = stereonet.f_cart2clar(
                x_pos, y_pos, projection=projection
            )
            if dipdir is None:
                return self.tr(
                    "plot.outside",
                    radius=np.sqrt(x_pos**2 + y_pos**2)
                )
            return self.tr(
                "plot.coord", dipdir=dipdir, dip=dip,
                projection=projection
            )

        ax.format_coord = poles_format_coord
        cmap = plt.get_cmap("tab10")
        fam_int = fam.astype(int)
        unique_fams = sorted(np.unique(fam_int).tolist())

        for family_id in unique_fams:
            mask = fam_int == family_id
            if family_id == 0:
                color = "0.6"
                label = self.tr("plot.unclassified")
                zorder = 0
            else:
                color = cmap((family_id - 1) % 10 / 10)
                label = f"J_{family_id}"
                zorder = 0
            ax.plot(
                xp[mask], yp[mask], ".", color=color,
                markersize=1.2, alpha=0.5,
                label=f"{label} ({int(np.sum(mask))} pts)",
                zorder=zorder
            )

        for pole in self.principal_poles:
            pole_x, pole_y = stereonet.f_clar2cart(
                pole["dipdir"], pole["dip"], projection=projection
            )
            pole_x = float(np.atleast_1d(pole_x)[0])
            pole_y = float(np.atleast_1d(pole_y)[0])
            index = pole.get("idx", 1)
            ax.plot(
                pole_x, pole_y, "ko", markersize=7,
                markerfacecolor="yellow", markeredgewidth=1.2,
                zorder=10
            )
            label = ax.text(
                pole_x + 0.035, pole_y + 0.025,
                f"$J_{{{index}}}$", fontsize=11,
                fontweight="bold", color="black", zorder=11
            )
            label.set_path_effects([
                path_effects.withStroke(
                    linewidth=2.5, foreground="white"
                )
            ])

        self.family_fig.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.92)
        ax.set_title(self.tr(
            "plot.family_title", count=len(xp), projection=projection
        ))
        self.family_fig.canvas.draw_idle()
        self.family_fig.canvas.flush_events()

    def run_plot_poles_by_family(self):
        cloud = self.get_selected_cloud()
        if cloud is None or cloud.getScalarFieldIndexByName("Discontinuity Set (DS)") < 0:
            messagebox.showwarning(
                self.tr("dialog.warning_title"), self.tr("dialog.classify_first")
            )
            return
        if not self._js_is_current():
            messagebox.showwarning(
                self.tr("dialog.outdated_title"), self.tr("dialog.reclassify")
            )
            return

        projection = self._canonical_projection()
        self.log(
            self.tr("log.extracting_family_labels", projection=projection)
        )
        xp, yp, fam = stereonet.project_poles_by_family(
            cloud, projection=projection
        )
        self.family_plot_data = (xp, yp, fam, projection)

        if (
            self.family_fig is None
            or not plt.fignum_exists(self.family_fig.number)
        ):
            plt.ion()
            self.family_fig, self.family_ax = plt.subplots(
                figsize=(7, 7)
            )

        self._refresh_family_plot_if_open(reload_data=False)
        unique_fams = sorted(np.unique(fam.astype(int)).tolist())
        self.log(self.tr(
            "log.plot_success", count=len(xp),
            families=len(unique_fams)
        ))
        plt.show(block=False)

    # ---------------------------------------------------------
    # STEP 3 EXECUTIONS
    # ---------------------------------------------------------
    def _create_family_cluster_result_clouds(self, source_cloud):
        js_index = source_cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
        cl_index = source_cloud.getScalarFieldIndexByName("Cluster id (cl)")
        if js_index < 0 or cl_index < 0:
            raise RuntimeError(self.tr("gui.source_js_cl_missing"))
        coordinates = np.asarray(source_cloud.points(), dtype=np.float64)
        js_values = np.asarray(
            source_cloud.getScalarField(js_index).asArray(), dtype=np.int32
        ).copy()
        scalar_names = ("Discontinuity Set (DS)", "Cluster id (cl)", "A", "B", "C", "D", "sigma")
        scalar_values = {}
        for name in scalar_names:
            index = source_cloud.getScalarFieldIndexByName(name)
            if index >= 0:
                scalar_values[name] = np.asarray(
                    source_cloud.getScalarField(index).asArray(), dtype=np.float32
                ).copy()

        group_name = self.tx(self.tr("gui.clustering_results"))
        group = pycc.ccHObject(
            group_name + " " + datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        created = 0
        for family_id in sorted(int(v) for v in np.unique(js_values) if v > 0):
            source_indices = np.flatnonzero(js_values == family_id)
            points = coordinates[source_indices].astype(pycc.PointCoordinateType)
            family_cloud = pycc.ccPointCloud(points[:,0], points[:,1], points[:,2])
            family_cloud.setName(f"J_{family_id} - clusters")

            for name, values in scalar_values.items():
                stereonet.write_scalar_field_cpp(
                    family_cloud, name, values[source_indices]
                )

            target_cl_index = family_cloud.getScalarFieldIndexByName("Cluster id (cl)")
            family_cloud.setCurrentScalarField(target_cl_index)
            family_cloud.setCurrentDisplayedScalarField(target_cl_index)
            family_cloud.showSF(True)
            try:
                family_cloud.showSFColorsScale(True)
            except Exception:
                pass
            try:
                source_sf = source_cloud.getScalarField(cl_index)
                target_sf = family_cloud.getScalarField(target_cl_index)
                target_sf.setColorScale(source_sf.getColorScale())
            except Exception:
                pass
            try:
                shift = source_cloud.getGlobalShift()
                family_cloud.setGlobalShift(
                    float(shift[0]), float(shift[1]), float(shift[2])
                )
                family_cloud.setGlobalScale(source_cloud.getGlobalScale())
            except Exception:
                pass
            family_cloud.setMetaData("DSE_Family", family_id)
            family_cloud.setMetaData("DSE_ActiveScalar", "Cluster id (cl)")
            group.addChild(family_cloud)
            created += 1
            self.log(
                self.tr("log.family_cloud_created", family=family_id, count=len(source_indices))
            )

        cc = pycc.GetInstance()
        cc.addToDB(group)
        cc.updateUI()
        cc.redrawAll()
        self.log(self.tr("log.family_clouds_group", count=created, group=group.getName()))
        return group

    def run_clusterize(self):
        self.cluster_planes_results = None
        self.btn_facets.config(state=tk.DISABLED)
        cloud = self.get_selected_cloud()
        if cloud is None:
            return
        if cloud.getScalarFieldIndexByName("Discontinuity Set (DS)") < 0:
            messagebox.showwarning(self.tx("Workflow Error"), self.tx("Step 2 incomplete: DS field missing."))
            return
        if not self._js_is_current():
            messagebox.showwarning(self.tr("dialog.outdated_title"), self.tr("dialog.reclassify"))
            return
        if not self.principal_poles:
            messagebox.showwarning(self.tx("Workflow Error"), self.tx("No principal poles. Run Step 1 first."))
            return

        try:
            k_neighbor = int(self.spin_k_neighbor.get())
            k_sigma = float(self.spin_k_sigma.get())
            dbscan_minpts = int(self.spin_dbscan_minpts.get())
            minimum_cluster_size = int(self.spin_min_cluster_size.get())
            merge_k_sigmas = float(self.spin_merge_sigma.get())
        except ValueError:
            messagebox.showerror(self.tx("Error"), self.tx("Enter valid numeric parameters."))
            return

        fix_orientation = bool(self.fix_orientation_var.get())
        sort_by = ("size", "D", "random")[max(0, self.sort_combo.current())]
        seed_text = self.ent_random_seed.get().strip()
        try:
            random_seed = None if seed_text == "" else int(seed_text)
        except ValueError:
            messagebox.showerror(self.tx("Error"), self.tx("Random seed must be an integer or blank."))
            return

        self._save_method_settings()
        self.log(self.tr("log.step3_header"))
        self.log(self.tr("log.scalar_writer_backend"))
        self.log(self.tr("log.cluster_params", k=k_neighbor, k_sigma=f"{k_sigma:.1f}", minpts=dbscan_minpts, minsize=minimum_cluster_size, merge=f"{merge_k_sigmas:.1f}", sort=sort_by, fix=fix_orientation))

        stats = None
        results = None
        stats_msg = None
        plane_msg = None

        progress_dialog = DSEProgressDialog(self.root, title=self.tx("Clusterize Progress"))

        def progress_callback(percent, status_text):
            return progress_dialog.update_progress(percent, status_text)

        operation_start = time.perf_counter()
        timings = {}
        merge_stats = {}
        try:
            stage_start = time.perf_counter()
            stats, results, analysis_msg = stereonet.run_dse_cluster_analysis(
                cloud, self.principal_poles,
                k_neighbor=k_neighbor, k_sigma=k_sigma,
                dbscan_minpts=dbscan_minpts,
                minimum_cluster_size=minimum_cluster_size,
                fix_orientation=fix_orientation, merge_k_sigmas=merge_k_sigmas,
                sort_by=sort_by, random_seed=random_seed,
                progress_callback=progress_callback
            )
            timings["Complete cluster analysis and scalar writing"] = (
                time.perf_counter() - stage_start
            )
            stats_msg = analysis_msg
            plane_msg = analysis_msg
        finally:
            progress_dialog.close()

        if stats is None:
            if stats_msg and "cancelled" in stats_msg.lower():
                self.log(self.tr("log.clustering_cancelled"))
                messagebox.showinfo(self.tx("Cancelled"), self.tx("Process cancelled by user."))
            else:
                messagebox.showerror(self.tx("Error"), self.tx(stats_msg) if stats_msg else self.tr("log.unknown_dbscan_error"))
                self.log(self.tx(stats_msg) if stats_msg else self.tr("log.unknown_dbscan_error"))
            return

        for fam_id in sorted(stats.keys()):
            info = stats[fam_id]
            self.log(
                self.tr("log.cluster_fam_stats", family=fam_id, eps=f"{info['eps']:.4f}", before=info['clusters_before_merge'], after=info['clusters_after_merge'], pts=info['pts'], noise=info['raw_noise'], rejected=info['rejected_points'], zero=info['zero_points'])
            )

        if results is None:
            if plane_msg and "cancelled" in plane_msg.lower():
                self.log(self.tr("log.plane_calc_cancelled"))
                messagebox.showinfo(self.tx("Cancelled"), self.tx("Process cancelled by user."))
            else:
                messagebox.showerror(self.tx("Error"), self.tx(plane_msg) if plane_msg else self.tr("log.unknown_plane_error"))
                self.log(self.tx(plane_msg) if plane_msg else self.tr("log.unknown_plane_error"))
            return

        self.log(self.tr("log.planes_computed"))
        if merge_k_sigmas > 0.0 and fix_orientation:
            self.log(self.tr("log.coplanarity_merge_complete"))
        elif merge_k_sigmas > 0.0:
            self.log(self.tr("log.coplanarity_merge_skipped"))
        for stage_name, seconds in timings.items():
            self.log(self.tr("log.timing_stage", stage=self.tx(stage_name), seconds=seconds))
        self.cluster_planes_results = results
        self._populate_cluster_fisher_tab(results)
        if self.export_family_clouds_var.get():
            try:
                self._create_family_cluster_result_clouds(cloud)
            except Exception as exc:
                self.log(self.tr("log.family_cloud_export_error", exc=exc))
                messagebox.showerror(self.tx("Family cloud export"), str(exc))

        # cl, A, B, C and D now exist. Refresh Tools menu immediately.
        self.check_cloud_and_update_workflow()
        CC = pycc.GetInstance()
        ui_start = time.perf_counter()
        CC.updateUI()
        self.log(self.tr("log.ui_refresh", seconds=time.perf_counter() - ui_start))
        redraw_start = time.perf_counter()
        CC.redrawAll()
        self.log(self.tr("log.redraw", seconds=time.perf_counter() - redraw_start))
        self._populate_cluster_planes_tab(results)
        self.notebook.tab(self.tab_planes, state="normal")
        self.notebook.tab(self.tab_cluster_fisher, state="normal")
        self.notebook.select(self.tab_planes)
        self.notebook.update_idletasks()
        self.btn_facets.config(state=tk.NORMAL)
        self.log(self.tr("log.timing_step3_total", seconds=time.perf_counter() - operation_start))

    def _cluster_rgb(self, cluster_id, maximum):
        maximum = max(1, int(maximum))
        position = 0.5 if maximum == 1 else (int(cluster_id) - 1) / float(maximum - 1)
        try:
            cmap = plt.get_cmap(self.facet_colormap)
        except (ValueError, KeyError):
            # The stored colormap name is not registered with matplotlib
            # (e.g. a leftover "cet_*" colorcet name from an old settings
            # file). Fall back to a safe default instead of failing every
            # single cluster, and warn once so the user can fix Settings.
            if not getattr(self, "_warned_bad_colormap", False):
                self._warned_bad_colormap = True
                self.log(
                    self.tr("gui.warning_colormap").format(self.facet_colormap)
                )
            self.facet_colormap = "turbo"
            cmap = plt.get_cmap(self.facet_colormap)
        red, green, blue, _ = cmap(position)
        return tuple(int(round(255 * value)) for value in (red, green, blue))

    def create_cluster_facets(self):
        """
        Create one planar CloudCompare mesh for every valid DSE cluster.

        The function uses:
            - Discontinuity Set (DS) to identify the family.
            - Cluster id (cl) to identify each cluster.
            - self.cluster_planes_results for the fitted normal.
            - stereonet.compute_cluster_convex_facet() to generate the
              planar boundary and its triangulation.

        A failure in one cluster does not stop the remaining clusters.
        """

        dialog_title = self.tr("dialog.facets_title")

        # -------------------------------------------------------------
        # 1. Validate the selected cloud and the cluster analysis
        # -------------------------------------------------------------

        cloud = self.get_selected_cloud()

        if cloud is None:
            messagebox.showwarning(
                dialog_title,
                self.tr("dialog.facets_missing")
            )
            return

        cluster_results = getattr(
            self,
            "cluster_planes_results",
            None
        )

        if not cluster_results:
            messagebox.showwarning(
                dialog_title,
                self.tr("dialog.facets_missing")
            )
            return

        start_time = time.perf_counter()

        try:
            facet_type = self._canonical_facet_type()
        except Exception:
            facet_type = "convex"

        valid_facet_types = {
            "convex",
            "disk",
            "ellipse",
            "rectangle"
        }

        if facet_type not in valid_facet_types:
            facet_type = "convex"

        self.log(self.tr("log.facets_start"))

        # -------------------------------------------------------------
        # 2. Read and validate the source cloud
        # -------------------------------------------------------------

        try:
            point_count = int(cloud.size())

            if point_count < 3:
                messagebox.showwarning(
                    dialog_title,
                    self.tr("dialog.facets_missing")
                )
                return

            coords = np.asarray(
                cloud.points(),
                dtype=np.float64
            )

            if (
                coords.ndim != 2
                or coords.shape[1] != 3
                or coords.shape[0] != point_count
            ):
                raise ValueError(
                    "The selected cloud does not contain a valid "
                    "N x 3 coordinate array."
                )

        except Exception as exc:
            error_message = self.tr("gui.coords_read_error", error=str(exc))
            self.log(error_message)
            messagebox.showerror(
                dialog_title,
                error_message
            )
            return

        # -------------------------------------------------------------
        # 3. Read the DSE scalar fields
        # -------------------------------------------------------------

        try:
            js_idx = cloud.getScalarFieldIndexByName(
                "Discontinuity Set (DS)"
            )
            cl_idx = cloud.getScalarFieldIndexByName(
                "Cluster id (cl)"
            )

            if js_idx < 0 or cl_idx < 0:
                messagebox.showwarning(
                    dialog_title,
                    self.tr("dialog.facets_missing")
                )
                return

            js_sf = cloud.getScalarField(js_idx)
            cl_sf = cloud.getScalarField(cl_idx)

            if js_sf is None or cl_sf is None:
                raise ValueError(
                    "The required scalar fields could not be accessed."
                )

            js_raw = np.asarray(
                js_sf.asArray(),
                dtype=np.float64
            ).reshape(-1)

            cl_raw = np.asarray(
                cl_sf.asArray(),
                dtype=np.float64
            ).reshape(-1)

            if (
                js_raw.size != point_count
                or cl_raw.size != point_count
            ):
                raise ValueError(
                    "The scalar fields do not have the same number "
                    "of values as the selected point cloud."
                )

            valid_scalar_values = (
                np.isfinite(js_raw)
                & np.isfinite(cl_raw)
            )

            # Invalid scalar values are assigned to zero and therefore
            # cannot accidentally be included in a valid cluster.
            js_vals = np.zeros(
                point_count,
                dtype=np.int64
            )
            cl_vals = np.zeros(
                point_count,
                dtype=np.int64
            )

            js_vals[valid_scalar_values] = np.rint(
                js_raw[valid_scalar_values]
            ).astype(np.int64)

            cl_vals[valid_scalar_values] = np.rint(
                cl_raw[valid_scalar_values]
            ).astype(np.int64)

        except Exception as exc:
            error_message = self.tr("gui.dse_scalar_error", error=str(exc))
            self.log(error_message)
            messagebox.showerror(
                dialog_title,
                error_message
            )
            return

        # -------------------------------------------------------------
        # 4. Prepare the CloudCompare hierarchy
        # -------------------------------------------------------------

        root_group = pycc.ccHObject(
            f"DSE_Cluster_Facets_{facet_type}_"
            f"{datetime.now().strftime('%H%M%S')}"
        )

        mesh_count = 0
        cloud_count = 0
        skipped = 0
        error_count = 0

        # Keep Python references until the hierarchy has been inserted
        # into the CloudCompare database.
        retained_objects = [
            root_group
        ]

        try:
            create_cluster_clouds = bool(
                self.create_cluster_clouds_var.get()
            )
        except Exception:
            create_cluster_clouds = False

        # -------------------------------------------------------------
        # 4bis. Pre-group point indices by (family, cluster) ONCE.
        #
        # Recomputing a full-cloud boolean mask inside the per-cluster
        # loop (js_vals == family) & (cl_vals == cluster) costs
        # O(N_points x N_clusters). For large clouds with many clusters
        # this made the button appear frozen. A single vectorized sort
        # groups every point in O(N log N), independent of the number
        # of clusters.
        # -------------------------------------------------------------

        group_start = time.perf_counter()

        valid_idx = np.flatnonzero(valid_scalar_values)
        cluster_index_map = {}

        if valid_idx.size > 0:
            fam_keys = js_vals[valid_idx].astype(np.int64)
            clu_keys = cl_vals[valid_idx].astype(np.int64)

            # Offset so that (family, cluster) pairs map to unique keys
            # regardless of negative/zero cluster ids.
            clu_offset = int(clu_keys.min())
            clu_span = int(clu_keys.max() - clu_offset) + 2
            fam_offset = int(fam_keys.min())
            combined = (
                (fam_keys - fam_offset).astype(np.int64) * clu_span
                + (clu_keys - clu_offset).astype(np.int64)
            )

            order = np.argsort(combined, kind="stable")
            sorted_combined = combined[order]
            sorted_points_idx = valid_idx[order]
            sorted_fam = fam_keys[order]
            sorted_clu = clu_keys[order]

            _, start_positions, counts = np.unique(
                sorted_combined, return_index=True, return_counts=True
            )

            for start, count in zip(start_positions, counts):
                fam = int(sorted_fam[start])
                clu = int(sorted_clu[start])
                cluster_index_map[(fam, clu)] = sorted_points_idx[
                    start:start + count
                ]

        self.log(
            "Grouped {clusters} cluster(s) from {pts} point(s) in "
            "{seconds:.3f} s.".format(
                clusters=len(cluster_index_map),
                pts=int(valid_idx.size),
                seconds=time.perf_counter() - group_start,
            )
        )

        # -------------------------------------------------------------
        # 5. Process every family independently
        # -------------------------------------------------------------

        for family_id in sorted(cluster_results.keys()):
            family_results = cluster_results.get(family_id)

            if not isinstance(family_results, dict):
                skipped += 1
                continue

            if not family_results:
                continue

            try:
                family_id_int = int(family_id)
            except (TypeError, ValueError):
                skipped += len(family_results)
                continue

            family_group = pycc.ccHObject(
                f"J_{family_id_int}"
            )

            family_mesh_count = 0

            try:
                positive_cluster_ids = [
                    int(cluster_id)
                    for cluster_id in family_results.keys()
                    if int(cluster_id) > 0
                ]
            except Exception:
                positive_cluster_ids = []

            max_cluster_id = max(
                positive_cluster_ids,
                default=1
            )

            # ---------------------------------------------------------
            # 6. Process every cluster in the family
            # ---------------------------------------------------------

            for cluster_id, info in sorted(
                family_results.items(),
                key=lambda item: int(item[0])
            ):
                try:
                    cluster_id_int = int(cluster_id)

                    if cluster_id_int <= 0:
                        skipped += 1
                        continue

                    if not isinstance(info, dict):
                        raise ValueError(
                            "The cluster-plane result is invalid."
                        )

                    if "normal" not in info:
                        raise ValueError(
                            "The cluster does not contain a fitted normal."
                        )

                    normal = np.asarray(
                        info["normal"],
                        dtype=np.float64
                    ).reshape(-1)

                    if normal.size != 3:
                        raise ValueError(
                            "The fitted normal does not have "
                            "three components."
                        )

                    if not np.all(np.isfinite(normal)):
                        raise ValueError(
                            "The fitted normal contains invalid values."
                        )

                    normal_length = float(
                        np.linalg.norm(normal)
                    )

                    if (
                        not np.isfinite(normal_length)
                        or normal_length
                        <= np.finfo(np.float64).eps
                    ):
                        raise ValueError(
                            "The fitted normal has zero length."
                        )

                    normal = normal / normal_length

                    cluster_indices = cluster_index_map.get(
                        (family_id_int, cluster_id_int),
                        np.empty(0, dtype=np.int64)
                    )

                    if cluster_indices.size < 3:
                        raise ValueError(
                            "The cluster contains fewer than "
                            "three valid points."
                        )

                    points = coords[cluster_indices]

                    finite_points = np.all(
                        np.isfinite(points),
                        axis=1
                    )

                    points = points[finite_points]

                    if points.shape[0] < 3:
                        raise ValueError(
                            "The cluster contains fewer than three "
                            "points with finite coordinates."
                        )

                    # -------------------------------------------------
                    # Build the planar boundary and triangulation
                    # -------------------------------------------------

                    facet, reason = (
                        stereonet.compute_cluster_convex_facet(
                            points,
                            normal,
                            facet_type=facet_type
                        )
                    )

                    if facet is None:
                        raise ValueError(
                            reason or
                            "The planar facet could not be generated."
                        )

                    if (
                        "vertices" not in facet
                        or "triangles" not in facet
                    ):
                        raise ValueError(
                            "The facet geometry is incomplete."
                        )

                    vertices_3d = np.asarray(
                        facet["vertices"],
                        dtype=np.float64
                    )

                    triangles = np.asarray(
                        facet["triangles"],
                        dtype=np.int64
                    )

                    if (
                        vertices_3d.ndim != 2
                        or vertices_3d.shape[1] != 3
                        or vertices_3d.shape[0] < 3
                    ):
                        raise ValueError(
                            "The generated facet vertices are invalid."
                        )

                    if not np.all(np.isfinite(vertices_3d)):
                        raise ValueError(
                            "The generated facet contains "
                            "non-finite vertices."
                        )

                    if (
                        triangles.ndim != 2
                        or triangles.shape[1] != 3
                        or triangles.shape[0] < 1
                    ):
                        raise ValueError(
                            "No valid triangles were generated."
                        )

                    if (
                        np.min(triangles) < 0
                        or np.max(triangles)
                        >= vertices_3d.shape[0]
                    ):
                        raise ValueError(
                            "The triangulation contains an invalid "
                            "vertex index."
                        )

                    # -------------------------------------------------
                    # Create the CloudCompare vertex cloud
                    # -------------------------------------------------

                    vertices_cc = vertices_3d.astype(
                        pycc.PointCoordinateType
                    )

                    vertices = pycc.ccPointCloud(
                        vertices_cc[:, 0],
                        vertices_cc[:, 1],
                        vertices_cc[:, 2]
                    )

                    vertices.setName(
                        f"J_{family_id_int}_"
                        f"CL_{cluster_id_int}_FacetVertices"
                    )

                    red, green, blue = self._cluster_rgb(
                        cluster_id_int,
                        max_cluster_id
                    )

                    colors = np.empty(
                        (vertices.size(), 3),
                        dtype=np.uint8
                    )
                    colors[:, 0] = red
                    colors[:, 1] = green
                    colors[:, 2] = blue

                    vertices.setColors(colors)
                    vertices.showColors(True)
                    vertices.setEnabled(False)

                    # -------------------------------------------------
                    # Create and populate the CloudCompare mesh
                    # -------------------------------------------------

                    mesh = pycc.ccMesh(vertices)

                    mesh.setName(
                        f"J_{family_id_int}_"
                        f"CL_{cluster_id_int}_"
                        f"{facet_type}_Facet"
                    )

                    triangles_added = 0

                    for triangle in triangles:
                        i1 = int(triangle[0])
                        i2 = int(triangle[1])
                        i3 = int(triangle[2])

                        # Degenerate triangles are ignored.
                        if i1 == i2 or i2 == i3 or i1 == i3:
                            continue

                        mesh.addTriangle(i1, i2, i3)
                        triangles_added += 1

                    if triangles_added <= 0:
                        raise ValueError(
                            "All generated triangles were degenerate."
                        )

                    # Do not reject the mesh using mesh.size() here.
                    # Some PythonRuntime builds do not update that value
                    # reliably before insertion into CloudCompare's DB.
                    actual_faces = triangles_added

                    # Keep the associated vertex cloud alive. Depending
                    # on the PythonRuntime version, ccMesh may or may not
                    # automatically expose ownership of the vertex cloud.
                    try:
                        mesh.addChild(vertices)
                    except Exception:
                        pass

                    try:
                        mesh.notifyGeometryUpdate()
                    except Exception:
                        try:
                            mesh.refreshBB()
                        except Exception:
                            pass

                    mesh.setEnabled(True)
                    mesh.showColors(True)

                    # -------------------------------------------------
                    # Store useful DSE metadata
                    # -------------------------------------------------

                    area = facet.get(
                        "area",
                        0.0
                    )
                    perimeter = facet.get(
                        "perimeter",
                        0.0
                    )

                    try:
                        area = float(area)
                    except (TypeError, ValueError):
                        area = 0.0

                    try:
                        perimeter = float(perimeter)
                    except (TypeError, ValueError):
                        perimeter = 0.0

                    mesh.setMetaData(
                        "DSE_Colormap",
                        str(self.facet_colormap)
                    )
                    mesh.setMetaData(
                        "DSE_FacetType",
                        facet_type
                    )
                    mesh.setMetaData(
                        "DSE_Family",
                        family_id_int
                    )
                    mesh.setMetaData(
                        "DSE_Cluster",
                        cluster_id_int
                    )
                    mesh.setMetaData(
                        "DSE_Area",
                        str(area)
                    )
                    mesh.setMetaData(
                        "DSE_Perimeter",
                        str(perimeter)
                    )
                    mesh.setMetaData(
                        "DSE_Faces",
                        int(actual_faces)
                    )
                    mesh.setMetaData(
                        "DSE_Vertices",
                        int(vertices.size())
                    )
                    mesh.setMetaData(
                        "DSE_SourcePoints",
                        int(points.shape[0])
                    )

                    family_group.addChild(mesh)

                    retained_objects.extend([
                        vertices,
                        mesh
                    ])

                    mesh_count += 1
                    family_mesh_count += 1

                    # -------------------------------------------------
                    # Optionally create the original cluster cloud
                    # -------------------------------------------------

                    if create_cluster_clouds:
                        points_cc = points.astype(
                            pycc.PointCoordinateType
                        )

                        cluster_cloud = pycc.ccPointCloud(
                            points_cc[:, 0],
                            points_cc[:, 1],
                            points_cc[:, 2]
                        )

                        cluster_cloud.setName(
                            f"J_{family_id_int}_"
                            f"CL_{cluster_id_int}_Cloud"
                        )

                        family_group.addChild(cluster_cloud)
                        retained_objects.append(cluster_cloud)
                        cloud_count += 1

                except Exception as exc:
                    skipped += 1
                    error_count += 1

                    reason = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    self.log(
                        self.tr(
                            "log.facets_skip",
                            family=family_id_int,
                            cluster=cluster_id,
                            reason=reason
                        )
                    )

                    # Continue with the next cluster.
                    continue

            # Add only families that contain at least one mesh.
            if family_mesh_count > 0:
                root_group.addChild(family_group)
                retained_objects.append(family_group)

        # -------------------------------------------------------------
        # 7. Insert the completed hierarchy into CloudCompare
        # -------------------------------------------------------------

        if mesh_count <= 0:
            elapsed = time.perf_counter() - start_time

            self.log(
                self.tr(
                    "log.facets_done",
                    meshes=0,
                    clouds=0,
                    skipped=skipped
                )
            )
            self.log(
                self.tr(
                    "log.facets_time",
                    seconds=elapsed
                )
            )

            messagebox.showwarning(
                dialog_title,
                self.tr("gui.no_planar_mesh_detail")
            )
            return

        try:
            CC = pycc.GetInstance()

            CC.addToDB(root_group)
            CC.updateUI()
            CC.redrawAll()

        except Exception as exc:
            error_message = self.tr(
                "gui.database_add_error",
                error=f"{type(exc).__name__}: {exc}"
            )

            self.log(error_message)

            messagebox.showerror(
                dialog_title,
                error_message
            )
            return

        # -------------------------------------------------------------
        # 8. Report the result
        # -------------------------------------------------------------

        elapsed = time.perf_counter() - start_time

        self.log(
            self.tr(
                "log.facets_done",
                meshes=mesh_count,
                clouds=cloud_count,
                skipped=skipped
            )
        )

        self.log(
            self.tr(
                "log.facets_time",
                seconds=elapsed
            )
        )

        if error_count > 0:
            messagebox.showinfo(
                dialog_title,
                self.tr(
                    "gui.mesh_result",
                    meshes=mesh_count, clouds=cloud_count, skipped=skipped
                )
            )
        else:
            messagebox.showinfo(
                dialog_title,
                self.tr("dialog.facets_done")
            )
            
    def _populate_cluster_planes_tab(self, results):
        for item in self.planes_tree.get_children():
            self.planes_tree.delete(item)

        total = 0
        for family_id in sorted(results.keys()):
            for cl_id, info in sorted(results[family_id].items()):
                A, B, C = info["normal"]
                self.planes_tree.insert("", tk.END, values=(
                    f"J_{family_id}", cl_id,
                    f"{info['dipdir']:.1f}", f"{info['dip']:.1f}",
                    f"{A:.4f}", f"{B:.4f}", f"{C:.4f}", f"{info['D']:.4f}",
                    info["n_pts"]
                ))
                total += 1

        self.log(self.tr("log.cluster_planes_listed", total=total))

    def _cluster_fisher_confidence_level(self):
        value = self.fisher_confidence_var.get()
        return int(value[:-1]) if value.endswith("%") else 0

    def _populate_cluster_fisher_tab(self, results):
        """Summarize axial Fisher dispersion of independently fitted planes."""
        self.cluster_fisher_results = []
        for family_id in sorted(results):
            clusters = list(results[family_id].items())
            if not clusters:
                continue
            cluster_id, reference = max(
                clusters, key=lambda item: item[1]["n_pts"]
            )
            reference_normal = np.asarray(
                reference["best_fit_normal"], dtype=float
            )
            reference_normal /= np.linalg.norm(reference_normal)
            normals = np.asarray(
                [info["best_fit_normal"] for _, info in clusters], dtype=float
            )
            normals /= np.linalg.norm(normals, axis=1)[:, None]
            normals[normals @ reference_normal < 0.0] *= -1.0
            count = len(normals)
            resultant_vector = normals.sum(axis=0)
            resultant = float(np.linalg.norm(resultant_vector))
            principal_normal = resultant_vector / max(
                resultant, np.finfo(float).eps
            )
            fisher_k = (
                float((count - 1) / max(1.0e-6, count - resultant))
                if count > 1 else 0.0
            )
            angles = np.degrees(np.arccos(np.clip(
                normals @ principal_normal, 0.0, 1.0
            )))
            dipdir, dip = stereonet.f_vnorm2clar_v02(
                principal_normal.reshape(1, 3)
            )
            self.cluster_fisher_results.append({
                "family_id": int(family_id), "normals": normals,
                "principal_normal": principal_normal,
                "principal_cluster": int(cluster_id), "N": count,
                "R": resultant, "K": fisher_k,
                "max_deviation": float(np.max(angles)) if count else 0.0,
                "furthest_index": int(np.argmax(angles)) if count else 0,
                "dipdir": float(dipdir[0]), "dip": float(dip[0]),
            })
        self._refresh_cluster_fisher_table()

    def _refresh_cluster_fisher_table(self, event=None):
        if not hasattr(self, "cluster_fisher_tree"):
            return
        for item in self.cluster_fisher_tree.get_children():
            self.cluster_fisher_tree.delete(item)
        confidence_level = self._cluster_fisher_confidence_level()
        for result in getattr(self, "cluster_fisher_results", []):
            confidence = 0.0
            if confidence_level and result["N"] >= 3 and result["K"] > 0.0:
                factor = 81.0 if confidence_level == 63 else 140.0
                confidence = factor / np.sqrt(result["K"] * result["N"])
            result["confidence"] = confidence
            self.cluster_fisher_tree.insert("", tk.END, values=(
                "DS {}".format(result["family_id"]),
                "{:.1f}".format(result["dipdir"]),
                "{:.1f}".format(result["dip"]), result["N"],
                "{:.2f}".format(result["K"]),
                "{:.1f}".format(result["max_deviation"]),
                "{:.1f}".format(confidence) if confidence > 0.0 else "-",
            ))

    def _draw_fisher_circle(self, axis, normal, radius_deg, projection, color,
                            linestyle="-", linewidth=1.5):
        if not 0.0 < radius_deg < 90.0:
            return
        normal = np.asarray(normal, dtype=float)
        reference = np.array([0.0, 0.0, 1.0])
        if abs(float(normal @ reference)) > 0.9:
            reference = np.array([1.0, 0.0, 0.0])
        axis_u = np.cross(reference, normal)
        axis_u /= np.linalg.norm(axis_u)
        axis_v = np.cross(normal, axis_u)
        angles = np.linspace(0.0, 2.0 * np.pi, 181)
        radius = np.radians(radius_deg)
        circle = (np.cos(radius) * normal + np.sin(radius) * (
            np.cos(angles)[:, None] * axis_u + np.sin(angles)[:, None] * axis_v
        ))
        # Keep the original azimuth and only fold the dip (abs), instead of
        # negating the whole vector: negating x/y/z rotates the azimuth by
        # 180 deg for the folded points, which is what produced the fake
        # diameters joining the two arcs.
        omega = np.arctan2(circle[:, 1], circle[:, 0])
        omega[omega < 0.0] += 2.0 * np.pi
        dipdir = np.degrees(np.pi / 2.0 - omega) % 360.0
        hypot = np.hypot(circle[:, 0], circle[:, 1])
        with np.errstate(divide="ignore", invalid="ignore"):
            dip = np.arctan(hypot / circle[:, 2])
        # Conversion vectorial equivalente a f_vnor2vbuz de MATLAB:
        # los vectores del hemisferio superior se llevan a su antipoda
        # en el inferior antes de proyectarlos.
        dipdir, dip_deg = stereonet.f_vnorm2clar_v02(circle)
        x, y = stereonet.f_clar2cart(
            dipdir, dip_deg, projection=projection
        )

        # Las dos ramas proyectadas son discontinuas al cruzar el borde
        # del primitivo. NaN impide que Matplotlib las una con un diametro.
        jump = np.hypot(np.diff(x), np.diff(y)) > 0.5
        breaks = np.flatnonzero(jump) + 1
        x = np.insert(x, breaks, np.nan)
        y = np.insert(y, breaks, np.nan)

        axis.plot(
            x, y, color=color, linestyle=linestyle, linewidth=linewidth
        )

    def plot_cluster_fisher_stereonet(self):
        if not getattr(self, "cluster_fisher_results", []):
            return
        self._refresh_cluster_fisher_table()
        projection = self._canonical_projection()
        figure, axis = plt.subplots(figsize=(8, 8))
        stereonet.draw_stereonet(axis, projection=projection,
                                 labeled=self.labeled_var.get())
        colors = plt.get_cmap("tab10")
        for index, result in enumerate(self.cluster_fisher_results):
            color = colors(index % 10)
            family_id = result["family_id"]

            dipdir, dip = stereonet.f_vnorm2clar_v02(result["normals"])
            x, y = stereonet.f_clar2cart(
                dipdir, dip, projection=projection
            )
            axis.scatter(
                x, y, s=36, color=color, marker="o",
                edgecolors="0.3", linewidths=0.5,
                label=self.tr("plot.cluster_normals", family=family_id), zorder=0
            )

            px, py = stereonet.f_clar2cart(
                result["dipdir"], result["dip"], projection=projection
            )
            axis.scatter(
                px, py, s=130, color=color, marker="p",
                edgecolors="black", linewidths=0.9, zorder=10,
                label=self.tr("plot.mean_pole", family=family_id)
            )

            self._draw_fisher_circle(
                axis, result["principal_normal"], result["max_deviation"],
                projection, color
            )
            if result.get("confidence", 0.0) > 0.0:
                self._draw_fisher_circle(
                    axis, result["principal_normal"], result["confidence"],
                    projection, "black", linestyle="--", linewidth=1.8
                )

        axis.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0.0,
            fontsize=9,
            title=self.tx("Principal pole")
        )
        axis.set_title(self.tr("Cluster-normal Fisher dispersion - [{projection}]", projection=projection))
        figure.tight_layout()
        plt.show(block=False)


    # ---------------------------------------------------------
    # AUXILIARY TABLE AND PLOT MANAGEMENT
    # ---------------------------------------------------------
    def _apply_fisher_results(self, fisher_results, provisional=False):
        label = "provisional" if provisional else "final"
        self.log(self.tr("log.fisher_heading", status=self.tr("status." + label)))
        for family_id, values in sorted(fisher_results.items()):
            if 1 <= family_id <= len(self.principal_poles):
                pole = self.principal_poles[family_id - 1]
                pole["fisher_k"] = values["K"]
                pole["fisher_n"] = values["N"]
                pole["fisher_r"] = values["R"]
                k_value = values["K"]
                if np.isnan(k_value):
                    k_text = "N/A"
                elif np.isinf(k_value):
                    k_text = "Inf"
                else:
                    k_text = f"{k_value:.2f}"
                self.log(self.tr("log.fisher_family", family=family_id, k=k_text, n=values["N"], r=values["R"]))

    def _renumber_principal_poles(self):
        for position, pole in enumerate(self.principal_poles, start=1):
            pole["idx"] = position
            pole["id"] = f"J_{position}"

    def _set_poles_status(self, status):
        self.poles_review_status = status
        if not hasattr(self, "lbl_poles_status"):
            return
        if status == "validated":
            text = self.tr("status.validated")
            background = "#d1e7dd"
            foreground = "#0f5132"
        elif status == "automatic":
            text = self.tr("status.auto")
            background = "#fff3cd"
            foreground = "#664d03"
        else:
            text = self.tr("status.empty")
            background = "#f2f2f7"
            foreground = "#6c757d"
        self.lbl_poles_status.config(
            text=text, bg=background, fg=foreground
        )

    def _invalidate_after_pole_change(self):
        self.poles_revision += 1
        self.js_revision = -1
        self.cluster_planes_results = None
        self.btn_facets.config(state=tk.DISABLED)
        self.log(self.tr("status.outdated") + ".")

    def _recalculate_fisher_for_current_table(self):
        cloud = self.get_selected_cloud(verbose=False)
        if cloud is None or not self.principal_poles:
            return
        try:
            cone = float(self.spin_js_cone.get())
            fisher = stereonet.compute_cloud_fisher_k(
                cloud, self.principal_poles,
                max_cone_angle_deg=cone
            )
            for family_id, values in fisher.items():
                if 1 <= family_id <= len(self.principal_poles):
                    pole = self.principal_poles[family_id - 1]
                    pole["fisher_k"] = values["K"]
                    pole["fisher_n"] = values["N"]
                    pole["fisher_r"] = values["R"]
        except Exception as exc:
            self.log(self.tr("log.fisher_refresh_warning", exc=exc))

    def _on_principal_poles_changed(
            self, selected_index=None, reason="manual"):
        self._renumber_principal_poles()
        if reason in ("edit", "add", "delete", "reorder"):
            self._rebuild_display_principal_poles()
        self._recalculate_fisher_for_current_table()
        self.update_table_view()
        self.refresh_plot()
        self._refresh_family_plot_if_open(reload_data=False)
        self._set_poles_status(
            "validated" if self.principal_poles else "empty"
        )
        self._invalidate_after_pole_change()
        self.check_cloud_and_update_workflow()

        if selected_index is not None and self.principal_poles:
            selected_index = max(
                0, min(selected_index, len(self.principal_poles) - 1)
            )
            item_id = str(selected_index)
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.tree.see(item_id)

    def _js_is_current(self):
        return (
            bool(self.principal_poles)
            and self.js_revision == self.poles_revision
        )

    def update_table_view(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, p in enumerate(self.principal_poles, start=1):
            p['idx'] = idx
            p['id'] = f"J_{idx}"
            self.tree.insert(
                "", tk.END, iid=str(idx - 1),
                values=(
                    p['id'], f"{p['dipdir']:.1f}", f"{p['dip']:.1f}",
                    f"{p['density']:.2f}",
                    "N/A" if np.isnan(p.get("fisher_k", np.nan)) else
                    ("Inf" if np.isinf(p.get("fisher_k", np.nan)) else f"{p.get('fisher_k'):.2f}"),
                    p.get("fisher_n", 0)
                )
            )
        self._update_pairwise_angles()

    def refresh_plot(self):
        if not self.cached_density_grids:
            return

        projection = self.cached_projection or self._canonical_projection()
        selected_space = (
            "rotated" if self._use_rotated_pole_space() else "original"
        )
        if selected_space not in self.cached_density_grids:
            selected_space = "original"
        X, Y, Z = self.cached_density_grids[selected_space]
        rotated_space = selected_space == "rotated"
        labeled = 0 if rotated_space else self.labeled_var.get()
        filled = (self._canonical_density_style() == "Filled Contours")
        self._rebuild_display_principal_poles(selected_space)

        if self.fig is None or not plt.fignum_exists(self.fig.number):
            plt.ion()
            self.fig, self.ax = plt.subplots(figsize=(7.5, 7.5))
            self.cbar = None

        cf = stereonet.draw_density_from_grid(
            self.ax, X, Y, Z,
            projection=projection, labeled=labeled, filled=filled,
            principal_poles=self.display_principal_poles
        )

        if cf is not None:
            cf.set_clim(0.0, 100.0)
            density_ticks = [0, 25, 50, 75, 100]
            if self.cbar is None or self.cbar.ax not in self.fig.axes:
                self.cbar = self.fig.colorbar(
                    cf, ax=self.ax, orientation="vertical",
                    shrink=0.8, ticks=density_ticks
                )
            else:
                self.cbar.update_normal(cf)
                self.cbar.set_ticks(density_ticks)
            self.cbar.set_ticklabels(["0", "25", "50", "75", "100"])
            self.cbar.set_label(self.tr("table.density"))
            self.cbar.ax.set_ylim(0.0, 100.0)

        space_name = self.tx("Rotated space") if rotated_space else self.tx("Original space")
        self.ax.set_title(
            self.tr("plot.density_title", projection=projection)
            + " - " + space_name
        )
        self.fig.canvas.draw_idle()
        plt.show(block=False)

    def on_pole_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return

        idx = int(selected[0])
        p = self.principal_poles[idx]

        self.ent_dipdir.delete(0, tk.END)
        self.ent_dipdir.insert(0, f"{p['dipdir']:.1f}")

        self.ent_dip.delete(0, tk.END)
        self.ent_dip.insert(0, f"{p['dip']:.1f}")

    def action_update_pole(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                self.tx("Information"), self.tx("Select a pole in the table to edit.")
            )
            return
        idx = int(selected[0])
        try:
            new_dipdir = float(self.ent_dipdir.get()) % 360.0
            new_dip = float(self.ent_dip.get())
        except ValueError:
            messagebox.showerror(
                self.tx("Error"), self.tx("Enter valid Dip Direction and Dip values.")
            )
            return
        if not 0.0 <= new_dip <= 90.0:
            messagebox.showerror(self.tx("Error"), self.tx("Dip must be between 0 and 90 degrees."))
            return

        updated_pole = stereonet.create_pole_dict(
            new_dipdir, new_dip,
            projection=self._canonical_projection(),
            X=self.cached_X, Y=self.cached_Y, Z=self.cached_Z,
            idx=idx + 1
        )
        self.principal_poles[idx] = updated_pole
        self.log(
            self.tr("log.pole_updated", index=idx + 1, dipdir=f"{new_dipdir:.1f}", dip=f"{new_dip:.1f}")
        )
        self._on_principal_poles_changed(idx, reason="edit")

    def action_move_up(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx <= 0:
            return
        self.principal_poles[idx - 1], self.principal_poles[idx] = (
            self.principal_poles[idx], self.principal_poles[idx - 1]
        )
        self.log(self.tr("log.pole_moved", source=f"J_{idx + 1}", target=f"J_{idx}"))
        self._on_principal_poles_changed(idx - 1, reason="reorder")

    def action_move_down(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx >= len(self.principal_poles) - 1:
            return
        self.principal_poles[idx], self.principal_poles[idx + 1] = (
            self.principal_poles[idx + 1], self.principal_poles[idx]
        )
        self.log(self.tr("log.pole_moved", source=f"J_{idx + 1}", target=f"J_{idx + 2}"))
        self._on_principal_poles_changed(idx + 1, reason="reorder")

    def action_delete_pole(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(self.tx("Information"), self.tx("Select a pole to delete."))
            return
        idx = int(selected[0])
        removed_id = self.principal_poles[idx].get("id", f"J_{idx + 1}")
        del self.principal_poles[idx]
        self.log(self.tr("log.pole_deleted", id=removed_id))
        next_index = min(idx, len(self.principal_poles) - 1)
        self._on_principal_poles_changed(
            next_index if next_index >= 0 else None,
            reason="delete"
        )

    def action_add_pole(self):
        try:
            dipdir = float(self.ent_dipdir.get()) % 360.0
            dip = float(self.ent_dip.get())
        except ValueError:
            messagebox.showerror(
                self.tx("Error"), self.tx("Enter valid Dip Direction and Dip values.")
            )
            return
        if not 0.0 <= dip <= 90.0:
            messagebox.showerror(self.tx("Error"), self.tx("Dip must be between 0 and 90 degrees."))
            return

        new_idx = len(self.principal_poles) + 1
        new_pole = stereonet.create_pole_dict(
            dipdir, dip,
            projection=self._canonical_projection(),
            X=self.cached_X, Y=self.cached_Y, Z=self.cached_Z,
            idx=new_idx
        )
        self.principal_poles.append(new_pole)
        self.log(
            self.tr("log.pole_added", index=new_idx, dipdir=f"{dipdir:.1f}", dip=f"{dip:.1f}", density=f"{new_pole['density']:.2f}")
        )
        self._on_principal_poles_changed(new_idx - 1, reason="add")


_enable_windows_dpi_awareness()
root = tk.Tk()
try:
    # Keep Tk scaling coherent with the actual monitor DPI.
    dpi = float(root.winfo_fpixels("1i"))
    root.tk.call("tk", "scaling", max(1.0, dpi / 72.0))
except Exception:
    pass
app = DSEMainApp(root)
root.mainloop()
