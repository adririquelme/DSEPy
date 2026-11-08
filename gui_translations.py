# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk


class _TranslationMixin:
    def tr(self, key, **values):
        template=self.i18n.get(key,default=key)
        try: return template.format(**values)
        except (KeyError,IndexError,ValueError): return template

    def tx(self, text):
        return self.i18n.get(text,default=text)

    def _refresh_action_labels(self):
        """Apply compact icons and localized descriptive button text."""
        labels = {
            "poles": self.tr("action.poles", default="\u25ce  Plot Poles"),
            "density": self.tr("action.density", default="\u2699  Density and Principal Poles"),
            "classify": self.tr("action.classify", default="\u2713  Classify Point Cloud (JS)"),
            "families": self.tr("action.families", default="\u25c9  Poles by Family (JS)"),
            "cluster": self.tr("action.cluster", default="\u25a6  Run Cluster Analysis"),
            "facets": self.tr("action.facets", default="\u25b3  Create Cluster Facets"),
            "add": self.tr("action.add", default="+  Add Pole"),
            "apply": self.tr("action.apply", default="\u2713  Apply Changes"),
            "delete": self.tr("action.delete", default="-  Delete Pole"),
            "up": self.tr("action.up", default="\u2191  Move Up"),
            "down": self.tr("action.down", default="\u2193  Move Down"),
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
        if hasattr(self, "poles_frame"):
            self.poles_frame.configure(text=" " + self.tx("gui.principal_pole_analysis") + " ")
        if hasattr(self, "grp_step1"):
            self.grp_step1.configure(text=" " + self.tx("gui.principal_poles") + " ")
        if hasattr(self, "grp_step2"):
            self.grp_step2.configure(text=" " + self.tx("gui.step2") + " ")
        if hasattr(self, "grp_step3"):
            self.grp_step3.configure(text=self.tx("Spatial clustering and plane fitting"))
        if hasattr(self, "cluster_parameters"):
            self.cluster_parameters.configure(text=" " + self.tx("Cluster analysis") + " ")
        if hasattr(self, "plane_parameters"):
            self.plane_parameters.configure(text=" " + self.tx("Plane calculation") + " ")
        if hasattr(self, "facet_export"):
            self.facet_export.configure(text=" " + self.tx("Facet export") + " ")
        if hasattr(self, "facet_type_combo"):
            current_facet = self._canonical_facet_type()
            facet_values = (self.tx("facet.type.convex"), self.tx("facet.type.disk"), self.tx("facet.type.ellipse"), self.tx("facet.type.rectangle"))
            self.facet_type_combo.configure(values=facet_values)
            self.facet_type_combo.set({
                "convex": self.tx("facet.type.convex"), "disk": self.tx("facet.type.disk"),
                "ellipse": self.tx("facet.type.ellipse"), "rectangle": self.tx("facet.type.rectangle"),
            }.get(current_facet, current_facet))
        if hasattr(self, "clustering_method_combo"):
            method = self._canonical_clustering_method()
            self.clustering_method_combo.configure(values=(
                self.tx("DBSCAN"), self.tx("HDBSCAN")
            ))
            self.clustering_method_combo.set(self.tx(method))
        if hasattr(self, "hdbscan_selection_combo"):
            selection = self._canonical_hdbscan_selection()
            self.hdbscan_selection_combo.configure(values=(
                self.tx("EOM"), self.tx("Leaf")
            ))
            self.hdbscan_selection_combo.set(self.tx(selection))
            self._update_clustering_controls()

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
        self.root.title(f"DSE - Discontinuity Set Extractor {self.DSE_VERSION}")

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

    def _refresh_menu_language(self):
        """Refresh labels and the available-language list after each reload."""
        try:
            self.menu_bar.entryconfig(self.tools_menu_index, label=self.tx("Tools"))
            self.menu_bar.entryconfig(self.settings_menu_index, label=self.tx("Settings"))
            self.menu_bar.entryconfig(self.language_menu_index, label=self._language_menu_label())
            self.menu_bar.entryconfig(self.about_menu_index, label=self.tx("About"))
            self.tools_menu.entryconfig(0, label=self.tx("Normal Colour Optimisation..."))
            self.tools_menu.entryconfig(1, label=self.tx("Spectral Clustering..."))
            for index, key in zip((3, 4), ("Normal Spacing...", "Persistence...")):
                self.tools_menu.entryconfig(index, label=self.tx(key))
            self.tools_menu.entryconfig(6, label=self.tx("Technical Report..."))
            self._rebuild_language_menu()
        except Exception:
            pass
