# -*- coding: utf-8 -*-

import json
import os
import tkinter as tk

import matplotlib.pyplot as plt


class _ConfigurationMixin:
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
            "clustering_method": "DBSCAN", "hdbscan_min_samples": 4,
            "hdbscan_selection": "EOM",
            "fix_orientation": 1, "sort_index": 0,
            "random_seed": "", "create_clouds": 1,
            "export_family_clouds": 1,
            "report_author": "", "report_client": "", "report_location": "",
            "report_version": "1.0", "report_observations": "",
            "report_folder": "", "report_formats": "html",
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
            "clustering_method": self._canonical_clustering_method(),
            "hdbscan_min_samples": int(self.spin_hdbscan_min_samples.get()),
            "hdbscan_selection": self._canonical_hdbscan_selection(),
            "merge_sigma": float(self.spin_merge_sigma.get()),
            "fix_orientation": int(self.fix_orientation_var.get()),
            "sort_index": int(self.sort_combo.current()), "random_seed": self.ent_random_seed.get().strip(),
            "create_clouds": int(self.create_cluster_clouds_var.get()),
            "export_family_clouds": int(self.export_family_clouds_var.get()),
            "report_author": self.report_meta["author"],
            "report_client": self.report_meta["client"],
            "report_location": self.report_meta["location"],
            "report_version": self.report_meta["report_version"],
            "report_observations": self.report_meta["observations"],
            "report_folder": self.report_meta["folder"],
            "report_formats": self.report_meta["formats"],
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
        self.clustering_method_combo.set(self.tx(s["clustering_method"]))
        self._set_control(self.spin_hdbscan_min_samples, s["hdbscan_min_samples"])
        self.hdbscan_selection_combo.set(self.tx(s["hdbscan_selection"]))
        self._update_clustering_controls()
        self._set_control(self.spin_merge_sigma, s["merge_sigma"])
        self.fix_orientation_var.set(s["fix_orientation"])
        self.sort_combo.current(min(max(int(s["sort_index"]), 0), 2))
        self._set_control(self.ent_random_seed, s["random_seed"])
        self.create_cluster_clouds_var.set(s["create_clouds"])
        self.export_family_clouds_var.set(s.get("export_family_clouds", 1))

    def _on_close(self):
        try: self._save_method_settings()
        except Exception: pass
        self.root.destroy()
