# -*- coding: utf-8 -*-

import json

import numpy as np

import colour_optimisation as colour_opt
import stereonet


class _StateMixin:
    def _read_cloud_state(self, cloud):
        try:
            if not cloud.hasMetaData(self.STATE_KEY):
                return {}
            state = json.loads(str(cloud.getMetaData(self.STATE_KEY)))
            if isinstance(state, dict) and state.get("version") == self.STATE_VERSION:
                return state
        except Exception as exc:
            self.log("State: could not read the saved DSE state ({})".format(exc))
        return {}

    def _save_cloud_state(self, section, cloud=None):
        """Overwrite one section ("colour" or "step1") of the cloud's DSE state."""
        try:
            cloud = cloud or self.get_selected_cloud(verbose=False)
            if cloud is None:
                return
            if section == "colour":
                if self.optimised_colour_rotation is None:
                    return
                data = dict(self._pending_colour_state)
                data.update({
                    "angles": self.optimised_colour_angles,
                    "rotation": self.optimised_colour_rotation,
                    "objective": self.optimised_colour_objective,
                    "objective_name": self.optimised_colour_objective_name,
                    "evaluations": self.optimised_colour_evaluations,
                    "iterations": self.optimised_colour_iterations,
                    "seconds": self.optimised_colour_seconds,
                })
            elif section == "step1":
                js_record = self.report_records.get("step2")
                js_state = None
                if (self._js_is_current() and js_record
                        and js_record.get("revision") == self.poles_revision):
                    js_state = {"cone": js_record["cone"], "counts": js_record["counts"]}
                data = {
                    "projection": self.cached_projection or self._canonical_projection(),
                    "space": self.cached_pole_space,
                    "status": self.poles_review_status,
                    "params": {
                        "bins": int(self.spin_bins.get()),
                        "min_angle": float(self.spin_angle.get()),
                        "max_poles": int(self.spin_maxpoles.get()),
                    },
                    "js": js_state,
                    "poles": [
                        {key: pole[key] for key in (
                            "dipdir", "dip", "density", "normal",
                            "fisher_k", "fisher_n", "fisher_r") if key in pole}
                        for pole in self.principal_poles
                    ],
                }
            else:
                return
            state = self._read_cloud_state(cloud)
            state.update({
                "version": self.STATE_VERSION,
                "software_version": self.DSE_VERSION,
                "points": int(cloud.size()),
                section: data,
            })
            cloud.setMetaData(
                self.STATE_KEY, json.dumps(state, default=self._state_json_default))
            self._state_cloud_id = cloud.getUniqueID()
        except Exception as exc:
            self.log("State: could not save the DSE state in the cloud ({})".format(exc))

    def _restore_cloud_state(self, cloud):
        """Load the colour rotation and principal poles saved in the cloud, if any."""
        state = self._read_cloud_state(cloud)
        if not state:
            return
        if int(state.get("points", -1)) != int(cloud.size()):
            self.log("State: the saved DSE state was ignored because the number of "
                     "points of the cloud has changed.")
            return
        restored = []
        colour = state.get("colour")
        if colour:
            try:
                self.optimised_colour_angles = np.asarray(colour["angles"], dtype=np.float64)
                self.optimised_colour_rotation = np.asarray(colour["rotation"], dtype=np.float64)
                self.optimised_colour_objective = float(colour["objective"])
                self.optimised_colour_objective_name = colour.get("objective_name")
                self.optimised_colour_evaluations = int(colour.get("evaluations") or 0)
                self.optimised_colour_iterations = int(colour.get("iterations") or 0)
                self.optimised_colour_seconds = float(colour.get("seconds") or 0.0)
                self._pending_colour_state = {
                    key: colour[key] for key in ("manual", "params") if key in colour}
                if self.pole_space_var is not None:
                    self.pole_space_combo.configure(state="readonly")
                restored.append(self.tr("report.sec.colour"))
                self._record_restored_colour(cloud, colour)
            except Exception as exc:
                self.log("State: colour rotation not restored ({})".format(exc))
        step1 = state.get("step1")
        if step1 and step1.get("poles"):
            try:
                projection = step1.get("projection") or self._canonical_projection()
                poles = []
                for index, saved in enumerate(step1["poles"], start=1):
                    pole = stereonet.create_pole_dict(
                        float(saved["dipdir"]), float(saved["dip"]),
                        projection=projection, idx=index)
                    pole["density"] = float(saved.get("density", 0.0))
                    if "normal" in saved:
                        pole["normal"] = np.asarray(saved["normal"], dtype=float)
                    for key in ("fisher_k", "fisher_n", "fisher_r"):
                        if key in saved:
                            pole[key] = saved[key]
                    poles.append(pole)
                self.principal_poles = poles
                self.cached_projection = projection
                self.cached_pole_space = step1.get("space") or "original"
                self.cached_X = self.cached_Y = self.cached_Z = None
                self.cached_density_grids = {}
                self._rebuild_display_principal_poles(self.cached_pole_space)
                self.update_table_view()
                self._set_poles_status(
                    "validated" if step1.get("status") == "validated" else "automatic")
                restored.append(self.tr("report.sec.step1"))
            except Exception as exc:
                self.log("State: principal poles not restored ({})".format(exc))
        if restored:
            self.poles_revision += 1
            self.js_revision = -1
            self.cluster_planes_results = None
            if step1 and step1.get("poles") and self.principal_poles:
                js_state = step1.get("js")
                has_ds = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)") >= 0
                if js_state and has_ds:
                    # The classification of the saved poles is still stored in the cloud.
                    self.js_revision = self.poles_revision
                    restored.append(self.tr("report.sec.step2"))
                self._restored_report_params = {
                    "cloud_id": cloud.getUniqueID(),
                    "params": step1.get("params") or {},
                    "projection": step1.get("projection") or self._canonical_projection(),
                    "space": step1.get("space") or "original",
                    "js": js_state if (js_state and has_ds) else None,
                }
                self._restored_step1 = self._restored_report_params
            self.log("State: restored from the cloud '{}': {}".format(
                cloud.getName(), "; ".join(restored)))

    def _ensure_density_cache(self, cloud):
        """Compute the Step 1 density of a restored cloud (once) so it can be plotted."""
        if self.cached_density_grids:
            return True
        pending = self._restored_step1
        if (not pending or not self.principal_poles
                or cloud.getUniqueID() != pending["cloud_id"]):
            return False
        params = pending["params"]
        projection = pending["projection"]
        bins_level = int(params.get("bins", self.spin_bins.get()))
        grid_res = 2 ** bins_level
        self.log("Restored state: computing the pole density of the cloud...")
        coordinates = {"original": stereonet.project_poles(cloud, projection=projection)}
        if self.optimised_colour_rotation is not None:
            coordinates["rotated"] = self._rotated_projected_poles(cloud, projection)
        space = pending["space"] if pending["space"] in coordinates else "original"
        grids = {
            name: stereonet.compute_density_grid(x, y, grid_res=grid_res, mindensity=1e-3)
            for name, (x, y) in coordinates.items()
        }
        self.cached_X, self.cached_Y, self.cached_Z = grids[space]
        self.cached_xp, self.cached_yp = coordinates[space]
        self.cached_projection = projection
        self.cached_pole_space = space
        self.cached_density_grids = grids
        self._restored_coordinates = coordinates
        return True

    def _rebuild_restored_reports(self):
        """Recreate the Step 1 / Step 2 report records of a restored cloud (done once, on demand)."""
        pending = self._restored_report_params
        if not pending or not self.principal_poles:
            return
        cloud = self.get_selected_cloud(verbose=False)
        if cloud is None or cloud.getUniqueID() != pending["cloud_id"]:
            return
        self._restored_report_params = None
        try:
            params = pending["params"]
            projection = pending["projection"]
            bins_level = int(params.get("bins", self.spin_bins.get()))
            min_angle = float(params.get("min_angle", self.spin_angle.get()))
            max_poles = int(params.get("max_poles", self.spin_maxpoles.get()))
            self._ensure_density_cache(cloud)
            coordinates = getattr(self, "_restored_coordinates", None)
            if not coordinates or not self.cached_density_grids:
                return
            space = self.cached_pole_space
            self._record_step1_report(
                cloud, projection, bins_level, 2 ** bins_level, min_angle, max_poles,
                space, coordinates, self.cached_density_grids)
            js_state = pending.get("js")
            if js_state and self._js_is_current():
                self._record_step2_report(
                    cloud, {int(k): int(v) for k, v in js_state["counts"].items()},
                    float(js_state["cone"]))
        except Exception as exc:
            self.log("Report: restored steps could not be rebuilt ({})".format(exc))

    def _record_restored_colour(self, cloud, colour):
        """Rebuild the report record of a restored colour optimisation."""
        class _Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        params = dict(colour.get("params") or {})
        if not params:
            return
        variables = {key: _Value(value) for key, value in params.items()}
        angles = self.optimised_colour_angles
        result = colour_opt.OptimisationResult(
            angles=angles.copy(), rotation=self.optimised_colour_rotation.copy(),
            objective=self.optimised_colour_objective,
            equivalent_degrees=colour_opt.equivalent_degrees(
                self.optimised_colour_objective,
                self.optimised_colour_objective_name),
            evaluations=self.optimised_colour_evaluations,
            iterations=self.optimised_colour_iterations,
            seconds=self.optimised_colour_seconds, success=True, message="")
        self._record_colour_report(
            result, variables, stereonet.get_cloud_normals(cloud),
            manual=bool(colour.get("manual")))
