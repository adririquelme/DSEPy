import numpy as np
import pytest

import colour_optimisation as colour_opt
import report_generator as rg
import stereonet

PROJECTION = "Equal-angle"
ORIENTATIONS = [(30.0, 20.0), (150.0, 60.0), (270.0, 35.0)]


def _normals(n=300, seed=3):
    rng = np.random.default_rng(seed)
    blocks, labels = [], []
    for family, (dipdir, dip) in enumerate(ORIENTATIONS, start=1):
        dd = np.radians(dipdir + rng.normal(0, 4, n))
        dp = np.radians(np.clip(dip + rng.normal(0, 4, n), 1, 89))
        blocks.append(np.column_stack((np.sin(dp) * np.sin(dd), np.sin(dp) * np.cos(dd), np.cos(dp))))
        labels += [family] * n
    return np.vstack(blocks), np.array(labels)


def _poles():
    poles = []
    for index, (dipdir, dip) in enumerate(ORIENTATIONS, start=1):
        pole = stereonet.create_pole_dict(dipdir, dip, projection=PROJECTION, idx=index)
        pole["density"] = 100.0 - 10 * index
        pole.update(fisher_k=50.0 + index, fisher_n=300, fisher_r=299.0)
        poles.append(pole)
    return poles


def _fisher_item(family_id, pole):
    rng = np.random.default_rng(family_id)
    normal = np.asarray(pole["normal"], dtype=float)
    normals = normal + rng.normal(0, 0.05, (6, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    normals[normals @ normal < 0] *= -1
    mean = normals.sum(axis=0)
    mean /= np.linalg.norm(mean)
    dev = np.degrees(np.arccos(np.clip(normals @ mean, 0, 1)))
    dipdir, dip = stereonet.f_vnorm2clar_v02(mean.reshape(1, 3))
    return {"family_id": family_id, "normals": normals, "principal_normal": mean, "N": 6, "K": 80.0,
            "max_deviation": float(dev.max()), "dipdir": float(dipdir[0]), "dip": float(dip[0])}


def _full_data():
    normals, labels = _normals()
    dipdir, dip = stereonet.f_vnorm2clar_v02(normals)
    xp, yp = stereonet.f_clar2cart(dipdir, dip, projection=PROJECTION)
    angles = np.array([20.0, -10.0, 5.0])
    rotation = colour_opt.rotation_matrix(angles)
    rx, ry, _, valid = colour_opt.projected_poles_from_normals(normals, angles, projection=PROJECTION)
    grids = {"original": stereonet.compute_density_grid(xp, yp, grid_res=64),
             "rotated": stereonet.compute_density_grid(rx[valid], ry[valid], grid_res=64)}
    counts = {0: 10, 1: 300, 2: 300, 3: 290}
    planes = {f: {1: {"normal": tuple(p["normal"]), "D": 1.5 * f, "dipdir": p["dipdir"], "dip": p["dip"],
                      "sigma": 0.02, "n_pts": 200, "best_fit_normal": p["normal"]},
                  2: {"normal": tuple(p["normal"]), "D": 3.0 * f, "dipdir": p["dipdir"], "dip": p["dip"],
                      "sigma": 0.03, "n_pts": 100, "best_fit_normal": p["normal"]}}
              for f, p in enumerate(_poles(), start=1)}
    kde_x = np.linspace(0, 5, 50)
    spacing = {"family_id": 1, "groups": [{}, {}], "x_nonpersistent": kde_x, "kde_nonpersistent": np.exp(-kde_x),
               "x_full": kde_x, "kde_full": np.exp(-kde_x / 2), "mean": 1.5, "std": 0.2, "min": 1.0,
               "max": 2.0, "mode": 1.4, "max_density_spacing": 1.3, "mean_full": 1.6}
    return {
        "cloud": {"name": "Slope A", "points": 890, "bbox_min": [10.0, 20.0, 0.0], "bbox_max": [60.0, 45.0, 12.5]},
        "colour": {"params": {"space": "HSV", "lightness": "80", "objective": "rational_vertical_asymptote",
                              "subsample": "25", "iterations": "80", "population": "12", "seed": ""},
                   "objective_name": "rational_vertical_asymptote", "angles": angles, "rotation": rotation,
                   "objective": 0.0123, "equivalent_degrees": float("nan"), "evaluations": 900,
                   "iterations": 40, "seconds": 1.2, "success": True, "manual": False,
                   "projection": PROJECTION, "normals_sample": normals},
        "step1": {"projection": PROJECTION, "bins": 6, "grid_res": 64, "min_angle": 30.0, "max_poles": 5,
                  "density_style": "Contour Lines", "space": "rotated", "n_poles": len(xp),
                  "poles": {"original": (xp, yp), "rotated": (rx[valid], ry[valid])}, "grids": grids},
        "poles": _poles(), "poles_status": "validated",
        "step2": {"cone": 30.0, "counts": counts, "total": 900, "plot": (xp[:890], yp[:890], labels[:890]),
                  "projection": PROJECTION},
        "step3": {"method": "DBSCAN",
                  "params": {"k_neighbor": 4, "k_sigma": 2.0, "dbscan_minpts": 4, "minimum_cluster_size": 100,
                             "merge_sigma": 1.5, "fix_orientation": True, "sort_by": "size", "random_seed": None},
                  "stats": {f: {"pts": 300, "eps": 0.05, "clusters_before_merge": 3, "clusters_after_merge": 2,
                                "raw_noise": 5, "rejected_points": 3, "zero_points": 8} for f in (1, 2, 3)},
                  "results": planes,
                  "fisher": [_fisher_item(f, p) for f, p in enumerate(_poles()[:3], start=1)]},
        "spacing": {"params": {"bandwidth": 0.0, "minimum": 0.01, "tolerance": 1e-5},
                    "results": [spacing] + [dict(spacing, family_id=f, mean=1.5 + f) for f in (2, 3)]},
        "persistence": {"params": {"tolerance": 1e-5},
                        "rows": [{"family_id": 1, "plane_id": i, "cluster_ids": (i,), "D": 1.0 * i, "n_points": 50,
                                  "p_dip": 3.0, "p_strike": 4.0, "p_max": 5.0 + i, "area": 12.0} for i in range(1, 5)],
                        "summaries": [{"family_id": 1, "n_planes": 4, "mean_pmax": 7.5, "max_pmax": 9.0,
                                       "mean_pdip": 3.0, "mean_pstrike": 4.0, "mean_area": 12.0}]},
    }


@pytest.mark.parametrize("language", ["en", "es"])
def test_full_report_html_and_markdown(tmp_path, language):
    info = {"project": "Test / project", "author": "A. Author", "client": "Client", "language": language,
            "observations": "First paragraph.\n\nSecond <b>paragraph</b>.", "software_version": "1.0.3beta"}
    paths = rg.generate_report(_full_data(), info, str(tmp_path), formats=("html", "markdown"))
    assert [p.rsplit(".", 1)[-1] for p in paths] == ["html", "md"]
    text = open(paths[0], encoding="utf-8").read()
    assert "A. Author" in text and "Second &lt;b&gt;paragraph" in text
    assert "35.000" in text and "12.500" in text
    assert text.count("data:image/png;base64") >= 12
    markdown = open(paths[1], encoding="utf-8").read()
    assert "| --- " in markdown
    figures = list((tmp_path / "DSE_report_Test_project_files").glob("figure_*.png"))
    assert len(figures) >= 8


def test_sections_are_optional(tmp_path):
    data = {"cloud": {"name": "x", "points": 3}, "step1": None, "poles": _poles(),
            "persistence": _full_data()["persistence"]}
    doc = rg.build_document(data, {"language": "en"})
    kinds = [b[2] for b in doc.blocks if b[0] == "h" and b[1] == 1]
    assert any("Persistence" in k for k in kinds) and not any("Principal poles" in k for k in kinds)


def test_block_size_section_groups_sets_by_three():
    data = _full_data()
    doc = rg.build_document(data, {"language": "en"})
    titles = [b[2] for b in doc.blocks if b[0] == "h" and b[1] == 1]
    assert any("block size" in t for t in titles)
    data["spacing"]["results"] = data["spacing"]["results"][:2]
    titles = [b[2] for b in rg.build_document(data, {"language": "en"}).blocks if b[0] == "h" and b[1] == 1]
    assert not any("block size" in t for t in titles)


def test_block_size_uses_all_combinations_of_three():
    data = _full_data()
    data["spacing"]["results"].append(dict(data["spacing"]["results"][0], family_id=4))
    data["poles"] = _poles() + [stereonet.create_pole_dict(200.0, 50.0, projection=PROJECTION, idx=4)]
    doc = rg.build_document(data, {"language": "en"})
    headings = [b[2] for b in doc.blocks if b[0] == "h" and b[1] == 2 and b[2].startswith("C")]
    assert len(headings) == 4


def test_empty_data_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        rg.generate_report({"cloud": {}}, {}, str(tmp_path))
