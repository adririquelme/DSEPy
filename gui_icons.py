# -*- coding: utf-8 -*-

import os
import tkinter as tk

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None


class _IconMixin:
    def _icons_directory(self):
        return os.path.join(self._plugins_dir, "icons")

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
            3: "spacing",
            4: "persistence",
        }
        for index, name in tools_icons.items():
            icon = self.icons.get(name)
            if icon is not None:
                try:
                    self.tools_menu.entryconfig(index, image=icon, compound=tk.LEFT)
                except Exception:
                    pass

    def _icons_directory_v030(self):
        return os.path.join(self._plugins_dir, "icons")

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
            "spacing", "persistence", "imagen_rotacion", "imagen_HSV_icono",
            "spectral_clustering_icon1", "technical_report"
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
        button._dse_icon_image = icon  # type: ignore[attr-defined]
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
                    refresh_path, box_size=30, canvas_size=34
                )
            except Exception as exc:
                self.log(f"Icon load warning (refresh): {exc}")
        if refresh_icon is None:
            refresh_icon = self.icons.get("refresh")
        if refresh_icon is not None:
            self.btn_refresh_cloud.configure(
                image=refresh_icon, text="", compound=tk.CENTER,
                width=38, height=36, padx=2, pady=2
            )
            self.btn_refresh_cloud._dse_icon_image = refresh_icon  # type: ignore[attr-defined]
        else:
            self.btn_refresh_cloud.configure(
                text=self.tr("Refresh"), width=38, height=36,
                padx=2, pady=2, font=("Segoe UI", 8, "bold")
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
                button._dse_icon_image = icon  # type: ignore[attr-defined]
            else:
                button.configure(text=fallback, width=6, height=2)
        tools_icons = {
            0: "imagen_rotacion",
            1: "spectral_clustering_icon1",
            3: "spacing",
            4: "persistence",
            6: "technical_report",
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
