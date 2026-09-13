# -*- coding: utf-8 -*-
"""
DSE Stereonet, Density (Botev KDE2D), Coordinate Transformations,
Principal Poles Extraction, Discontinuity Set (JS) Classification, 
and Native SciPy DBSCAN Spatial Clustering (cl Field) Module.

Based on Adrian Riquelme's MATLAB implementation (Discontinuity Set Extractor)
Department of Civil Engineering, University of Alicante, Spain
"""

import sys
import numpy as np
import time
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from scipy.optimize import brentq
from scipy.ndimage import maximum_filter
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import gaussian_kde
from scipy.spatial import cKDTree, ConvexHull, QhullError, distance
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


_TRANSLATOR = None

def set_translator(translator):
    """Install the application translation function used by visible text."""
    global _TRANSLATOR
    _TRANSLATOR = translator


def _tr(key, **values):
    if _TRANSLATOR is None:
        text = key
    else:
        try:
            text = _TRANSLATOR(key, **values)
        except TypeError:
            text = _TRANSLATOR(key)
    try:
        return text.format(**values) if values else text
    except (KeyError, IndexError, ValueError):
        return text


class CalculationCancelledException(Exception):
    """Excepcion personalizada para capturar la cancelacion manual del usuario."""
    pass


# ---------------------------------------------------------
# Conversiones de Coordenadas DSE (Riquelme MATLAB 1:1)
# ---------------------------------------------------------
def o2a(omega):
    omega = np.asarray(omega, dtype=float) % (2.0 * np.pi)
    alfa = np.zeros_like(omega)

    I1 = (omega >= 0) & (omega < np.pi / 2.0)
    alfa[I1] = np.pi / 2.0 - omega[I1] + np.pi

    I2 = (omega >= np.pi / 2.0) & (omega < np.pi)
    alfa[I2] = np.pi - (omega[I2] - np.pi / 2.0)

    I3 = (omega >= np.pi) & (omega < 3.0 * np.pi / 2.0)
    alfa[I3] = np.pi / 2.0 - (omega[I3] - np.pi)

    I4 = (omega >= 3.0 * np.pi / 2.0) & (omega < 2.0 * np.pi)
    alfa[I4] = 7.0 * np.pi / 2.0 - omega[I4]

    return alfa


def f_vnorm2clar_v02(Normales):
    Normales = np.asarray(Normales, dtype=float).copy()
    if Normales.ndim == 1:
        Normales = Normales.reshape(1, 3)

    I_neg = Normales[:, 2] < 0
    Normales[I_neg, :] = Normales[I_neg, :] * (-1.0)

    n = Normales.shape[0]
    dipdir = np.zeros(n)
    dip = np.zeros(n)

    I_horiz = Normales[:, 2] == 1.0
    dipdir[I_horiz] = 0.0
    dip[I_horiz] = 0.0

    I_non_horiz = Normales[:, 2] < 1.0
    if np.any(I_non_horiz):
        N_sub = Normales[I_non_horiz]
        omega = np.arctan2(N_sub[:, 1], N_sub[:, 0])
        omega[omega < 0] += 2.0 * np.pi

        alpha = np.pi / 2.0 - omega
        alpha[alpha < 0] += 2.0 * np.pi
        dipdir[I_non_horiz] = alpha

    I_vert = Normales[:, 2] == 0.0
    dip[I_vert] = np.pi / 2.0

    I_non_vert = Normales[:, 2] != 0.0
    if np.any(I_non_vert):
        N_sub = Normales[I_non_vert]
        dip[I_non_vert] = np.arctan(
            np.sqrt(N_sub[:, 0]**2 + N_sub[:, 1]**2) / N_sub[:, 2]
        )

    dipdir_deg = dipdir * 180.0 / np.pi
    dip_deg = dip * 180.0 / np.pi

    return dipdir_deg, dip_deg


def f_clar2cart(dipdir, dip, projection="Equal-angle"):
    dipdir = np.asarray(dipdir, dtype=float)
    dip = np.asarray(dip, dtype=float)

    dipdir_rad = dipdir * np.pi / 180.0
    dip_rad = dip * np.pi / 180.0

    if projection == "Equal-angle":
        radio = np.tan(dip_rad / 2.0)
    elif projection == "Equal-area":
        radio = np.sqrt(2.0) * np.cos(np.pi / 2.0 - dip_rad / 2.0)
    elif projection == "Equal-proportion":
        radio = dip_rad / (np.pi / 2.0)
    else:
        radio = np.tan(dip_rad / 2.0)

    alfa = o2a(dipdir_rad)
    x = radio * np.cos(alfa)
    y = radio * np.sin(alfa)

    return x, y


def f_cart2clar(x, y, projection="Equal-angle"):
    r = np.sqrt(x**2 + y**2)
    if r > 1.0001:
        return None, None

    r = min(r, 1.0)

    alpha_rad = np.arctan2(y, x) % (2.0 * np.pi)
    alpha_deg = np.degrees(alpha_rad)

    dipdir_deg = (270.0 - alpha_deg) % 360.0

    if projection == "Equal-angle":
        dip_rad = 2.0 * np.arctan(r)
    elif projection == "Equal-area":
        dip_rad = 2.0 * np.arcsin(np.clip(r / np.sqrt(2.0), 0.0, 1.0))
    elif projection == "Equal-proportion":
        dip_rad = r * (np.pi / 2.0)
    else:
        dip_rad = 2.0 * np.arctan(r)

    dip_deg = np.degrees(dip_rad)
    return dipdir_deg, dip_deg


def f_pole2vnor_v02(poles_cart, projection="Equal-angle"):
    P = np.asarray(poles_cart, dtype=float)
    if P.ndim == 1:
        P = P.reshape(1, 2)

    px = P[:, 0]
    py = P[:, 1]
    avn = np.zeros_like(px)

    I1 = (px > 0) & (py > 0)
    avn[I1] = np.arctan(py[I1] / px[I1]) + np.pi

    I2 = (px < 0) & (py >= 0)
    avn[I2] = 2.0 * np.pi - np.arctan(-py[I2] / px[I2])

    I3 = (px < 0) & (py <= 0)
    avn[I3] = np.arctan(py[I3] / px[I3])

    I4 = (px >= 0) & (py < 0)
    avn[I4] = np.pi - np.arctan(-py[I4] / px[I4])

    rho = np.sqrt(px**2 + py**2)
    rho[rho > 1.0] = 1.0

    if projection == "Equal-angle":
        beta = 2.0 * np.arctan(rho)
    elif projection == "Equal-area":
        beta = 2.0 * np.arcsin(rho / np.sqrt(2.0))
    elif projection == "Equal-proportion":
        beta = rho * np.pi / 2.0
    else:
        beta = 2.0 * np.arctan(rho)

    alpha = np.pi / 2.0 - beta
    nxy = np.cos(alpha)

    N = np.zeros((len(px), 3))
    N[:, 0] = nxy * np.cos(avn)
    N[:, 1] = nxy * np.sin(avn)
    N[:, 2] = np.sin(alpha)

    I_center = (px == 0) & (py == 0)
    N[I_center] = [0.0, 0.0, 1.0]

    I_neg = N[:, 2] < 0
    N[I_neg] *= -1.0

    return N


def f_radio(beta, projection="Equal-angle"):
    if projection == "Equal-angle":
        return np.sin(beta) / (1.0 + np.cos(beta))
    elif projection == "Equal-area":
        return np.sqrt(2.0) * np.sin(beta / 2.0)
    elif projection == "Equal-proportion":
        return beta / (np.pi / 2.0)
    else:
        return np.sin(beta) / (1.0 + np.cos(beta))


# ---------------------------------------------------------
# Representacion Grafica del Estereograma
# ---------------------------------------------------------
def draw_stereonet(ax, projection="Equal-angle", labeled=1):
    N = 50
    theta_circle = np.linspace(0, 2 * np.pi, 2 * N)
    cx = np.cos(theta_circle)
    cy = np.sin(theta_circle)

    ax.plot([-1, 1], [0, 0], "-.k", lw=0.7, zorder=6)
    ax.plot([0, 0], [-1, 1], "-.k", lw=0.7, zorder=6)
    ax.plot(cx, cy, "--k", lw=1.0, zorder=7)
    ax.set_aspect("equal")
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.3)
    ax.axis("off")

    psi = np.linspace(0, 2 * np.pi, 2 * N)
    beta_deg = [15, 30, 45, 60, 75, 90]
    beta_rad = [np.radians(b) for b in beta_deg]

    for i in range(len(beta_rad) - 1):
        r = f_radio(beta_rad[i], projection)
        x = r * np.sin(psi)
        y = r * np.cos(psi)
        ax.plot(x, y, ":r", lw=0.7, zorder=6)

        if labeled == 1:
            ax.text(r, 0, str(beta_deg[i]), horizontalalignment="left", verticalalignment="bottom", fontsize=8)

    if labeled == 1:
        r90 = f_radio(beta_rad[-1], projection)
        ax.text(r90, 0, "90", horizontalalignment="left", verticalalignment="bottom", fontsize=8)

    alpha0 = np.arange(0, 2 * np.pi - np.pi / 24, np.pi / 6)
    alpha = np.pi / 2.0 - alpha0 + np.pi
    label_deg = np.arange(0, 360, 30)

    x_lbl = 1.2 * np.cos(alpha)
    y_lbl = 1.2 * np.sin(alpha)
    font_size = 9

    for i in range(len(alpha)):
        if labeled == 1:
            amp = 0.95
            val = label_deg[i]

            if val == 0:
                ax.text(x_lbl[i], y_lbl[i] * amp, "0=S", horizontalalignment="center", verticalalignment="top", fontsize=font_size)
            elif val == 180:
                ax.text(x_lbl[i], y_lbl[i] * amp, "180=N", horizontalalignment="center", verticalalignment="top", fontsize=font_size)
            elif val == 90:
                ax.text(x_lbl[i] * amp, y_lbl[i], "90=W", horizontalalignment="right", verticalalignment="center", fontsize=font_size)
            elif val == 270:
                ax.text(x_lbl[i] * amp, y_lbl[i], "270=E", horizontalalignment="left", verticalalignment="center", fontsize=font_size)
            else:
                align = "right" if (val > 0 and val < 180) else "left"
                ax.text(x_lbl[i], y_lbl[i], str(val), horizontalalignment=align, verticalalignment="center", fontsize=font_size)

                r15 = f_radio(np.radians(15), projection)
                xaux = [r15 * np.cos(alpha[i]), np.cos(alpha[i])]
                yaux = [r15 * np.sin(alpha[i]), np.sin(alpha[i])]
                ax.plot(xaux, yaux, "r:.", lw=0.5, zorder=6)

                xmark = [np.cos(alpha[i]), 1.05 * np.cos(alpha[i])]
                ymark = [np.sin(alpha[i]), 1.05 * np.sin(alpha[i])]
                ax.plot(xmark, ymark, "k-", lw=0.7, zorder=7)


def project_poles(cloud, projection="Equal-angle"):
    npts = cloud.size()
    if npts == 0:
        return np.array([]), np.array([])

    if not cloud.hasNormals():
        raise RuntimeError(_tr("error.no_normals"))

    normals = cloud.normals()
    if normals is None:
        raise RuntimeError(_tr("error.normals_unavailable"))

    dipdir, dip = f_vnorm2clar_v02(normals)
    xp, yp = f_clar2cart(dipdir, dip, projection=projection)

    return xp, yp


def project_poles_by_family(cloud, projection="Equal-angle"):
    """
    Lee las normales y el campo escalar 'Discontinuity Set (DS)' directamente desde CloudCompare.
    """
    npts = cloud.size()
    if npts == 0:
        return np.array([]), np.array([]), np.array([])

    if not cloud.hasNormals():
        raise RuntimeError(_tr("error.no_normals"))

    sf_idx = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    if sf_idx < 0:
        raise RuntimeError(_tr("error.ds_field_missing_classify"))

    normals = cloud.normals()
    if normals is None:
        raise RuntimeError(_tr("error.normals_unavailable"))

    dipdir, dip = f_vnorm2clar_v02(normals)
    xp, yp = f_clar2cart(dipdir, dip, projection=projection)

    sf = cloud.getScalarField(sf_idx)
    js_vals = np.array(sf.asArray(), dtype=np.float32)

    return xp, yp, js_vals


def plot_poles_by_family_on_ax(ax, xp, yp, js_vals, projection="Equal-angle", principal_poles=None, point_size=10, cmap_name="jet"):
    """
    Representacion grafica de polos asignados por familias (JS) usando un colormap continuo.
    
    - Puntos JS == 0: Gris neutro [0.5, 0.5, 0.5] (Sin clasificar / fuera de cono).
    - Puntos JS > 0: Asignacion automatica de color normalizando la familia k in [1, max_JS]
      en el rango [0.0, 1.0] sobre el colormap.
      Con 3 familias y colormap 'jet': J1 = Azul (0.0), J2 = Verde (0.5), J3 = Rojo (1.0).
    """
    ax.clear()

    js_vals = np.asarray(js_vals, dtype=int).ravel()
    npts = len(js_vals)

    puntos_cero_mask = (js_vals == 0)
    puntos_no_cero_mask = (js_vals > 0)

    # 1. Puntos con categoria 0 (Gris neutro - Sin clasificar / fuera de cono)
    if np.any(puntos_cero_mask):
        cnt_0 = np.sum(puntos_cero_mask)
        ax.scatter(
            xp[puntos_cero_mask], yp[puntos_cero_mask],
            s=point_size, c=[[0.5, 0.5, 0.5]], alpha=0.30,
            edgecolors="none", label=_tr("plot.family_unclassified", count=cnt_0), zorder=2
        )

    # 2. Puntos con categoria > 0 (Familias J_1, J_2, J_3...) mapeadas sobre el colormap
    if np.any(puntos_no_cero_mask):
        max_js = int(np.max(js_vals[puntos_no_cero_mask]))
        unique_families = np.sort(np.unique(js_vals[puntos_no_cero_mask]))
        
        cmap = plt.get_cmap(cmap_name)

        for fam_id in unique_families:
            mask_k = (js_vals == fam_id)
            cnt_k = np.sum(mask_k)

            # Normalizar el indice fam_id al rango [0.0, 1.0]
            if max_js == 1:
                t = 0.0  # Si solo hay 1 familia, toma el extremo inicial (Azul)
            else:
                t = (fam_id - 1) / (max_js - 1)

            color_k = cmap(t)

            ax.scatter(
                xp[mask_k], yp[mask_k],
                s=point_size, color=[color_k], alpha=0.80,
                edgecolors="none", label=_tr("plot.family_label", family=fam_id, count=cnt_k), zorder=3
            )

    draw_stereonet(ax, projection=projection, labeled=1)

    # 3. Destacar los polos principales con etiqueta
    if principal_poles:
        for p in principal_poles:
            px, py = p["x"], p["y"]
            idx_num = p.get("idx", 1)

            ax.plot(px, py, "ko", markersize=7, markerfacecolor="yellow", markeredgewidth=1.2, zorder=10)

            latex_label = f"$J_{{{idx_num}}}$"
            txt = ax.text(
                px + 0.035, py + 0.025, latex_label,
                fontsize=11, fontweight="bold", color="black", zorder=11
            )
            txt.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground="white")])

    ax.set_title(_tr("plot.family_title_full", projection=projection, count=npts), fontsize=10, pad=12)
# ---------------------------------------------------------
# Interactive 3D sphere plot for complete axial normals
# ---------------------------------------------------------

def plot_normals_on_sphere(normals, transparency=0.15, point_size=3.0):
    """Plot axial normals on an interactive PyVista sphere."""
    try:
        import pyvista as pv
    except Exception as exc:
        raise RuntimeError(
_tr("error.pyvista_import", executable=sys.executable, exc=exc)
        ) from exc

    normals = np.asarray(normals, dtype=np.float64)
    if normals.ndim != 2 or normals.shape[1] != 3:
        raise ValueError(_tr("error.normals_shape"))

    valid = np.all(np.isfinite(normals), axis=1)
    normals = normals[valid]
    lengths = np.linalg.norm(normals, axis=1)
    nonzero = lengths > np.finfo(float).eps
    normals = normals[nonzero]
    lengths = lengths[nonzero]
    if normals.size == 0:
        raise ValueError(_tr("error.no_valid_normals"))

    normals = normals / lengths[:, None]
    axial_normals = np.ascontiguousarray(
        np.vstack((normals, -normals)), dtype=np.float32
    )

    plotter = pv.Plotter(window_size=(900, 900))
    plotter.set_background("white")

    sphere = pv.Sphere(
        radius=1.0, theta_resolution=48, phi_resolution=24
    )
    plotter.add_mesh(
        sphere, color="white", opacity=float(transparency),
        smooth_shading=True, show_edges=False
    )
    plotter.add_mesh(
        sphere, style="wireframe", color="#4c72b0",
        opacity=0.55, line_width=1.0
    )

    angle = np.linspace(0.0, 2.0 * np.pi, 181)
    scale = 1.006
    circles = (
        np.column_stack((np.cos(angle), np.sin(angle), np.zeros_like(angle))),
        np.column_stack((np.sin(angle), np.zeros_like(angle), np.cos(angle))),
        np.column_stack((np.zeros_like(angle), np.sin(angle), np.cos(angle))),
    )
    for circle in circles:
        line = pv.lines_from_points(scale * circle, close=True)
        plotter.add_mesh(line, color="#c62828", line_width=2.0)

    points = pv.PolyData(axial_normals)
    plotter.add_mesh(
        points, color="#77a832", point_size=float(point_size),
        render_points_as_spheres=False, opacity=0.85
    )

    label_points = np.array([
        [0.0, 1.12, 0.0], [0.0, -1.12, 0.0],
        [1.12, 0.0, 0.0], [-1.12, 0.0, 0.0]
    ])
    plotter.add_point_labels(
        label_points, ["N", "S", "E", "W"],
        font_size=18, text_color="black", point_size=0,
        shape_color="white", shape_opacity=0.95,
        always_visible=True
    )

    plotter.add_axes(
        xlabel="X", ylabel="Y", zlabel="Z",
        line_width=2, labels_off=False
    )
    plotter.add_text(
        _tr("plot.normals_on_sphere"), position="upper_edge",
        font_size=14, color="black"
    )
    plotter.camera_position = [
        (2.4, 2.4, 1.8), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    ]
    plotter.enable_anti_aliasing("fxaa")
    plotter.show(title=_tr("plot.dse_normals_sphere"))
    return "PyVista", len(axial_normals)

# ---------------------------------------------------------
# Botev KDE2D (Calculo de Densidad en Estereograma)
# ---------------------------------------------------------
def ndhist_matlab(data, M):
    nrows, ncols = data.shape
    bins = np.floor(data * M).astype(int)
    bins = np.clip(bins, 0, M - 1)

    binned_data = np.zeros((M, M))
    np.add.at(binned_data, (bins[:, 0], bins[:, 1]), 1.0 / nrows)
    return binned_data


def dct2d_matlab(data):
    nrows, ncols = data.shape
    w = np.concatenate(([1.0], 2.0 * np.exp(-1j * np.arange(1, nrows) * np.pi / (2.0 * nrows))))
    weight = w[:, None]

    def dct1d(x):
        top = np.arange(0, nrows, 2)
        bottom = np.arange(nrows - 1 if nrows % 2 == 0 else nrows - 2, 0, -2)
        idx = np.concatenate((top, bottom))
        x_reorder = x[idx, :]
        return np.real(weight * np.fft.fft(x_reorder, axis=0))

    return dct1d(dct1d(data).T).T


def idct2d_matlab(data):
    nrows, ncols = data.shape
    w = np.exp(1j * np.arange(nrows) * np.pi / (2.0 * nrows))
    weights = w[:, None]

    def idct1d(x):
        y = np.real(np.fft.ifft(weights * x, axis=0))
        out = np.zeros((nrows, ncols))
        out[0::2, :] = y[:nrows // 2, :]
        out[1::2, :] = y[nrows // 2:, :][::-1, :]
        return out

    return idct1d(idct1d(data).T)


def kde2d(data, n=256, MIN_XY=None, MAX_XY=None):
    N = data.shape[0]
    n = int(2**np.ceil(np.log2(n)))

    if MIN_XY is None or MAX_XY is None:
        MAX = np.max(data, axis=0)
        MIN = np.min(data, axis=0)
        Range = MAX - MIN
        MAX_XY = MAX + Range / 4.0
        MIN_XY = MIN - Range / 4.0

    MIN_XY = np.array(MIN_XY, dtype=float)
    MAX_XY = np.array(MAX_XY, dtype=float)
    scaling = MAX_XY - MIN_XY

    transformed_data = (data - MIN_XY) / scaling
    initial_data = ndhist_matlab(transformed_data, n)
    a = dct2d_matlab(initial_data)

    I = (np.arange(n, dtype=float))**2
    A2 = a**2

    def K(s):
        prod = 1.0
        for k in range(1, 2 * s, 2):
            prod *= k
        return ((-1.0)**s) * prod / np.sqrt(2.0 * np.pi)

    def psi(s, Time):
        w = np.exp(-I * np.pi**2 * Time)
        w = np.concatenate(([w[0]], 0.5 * w[1:]))
        wx = w * (I**s[0])
        wy = w * (I**s[1])
        return ((-1.0)**sum(s)) * (wy @ A2 @ wx) * (np.pi**(2 * sum(s)))

    def func(s, t):
        if sum(s) <= 4:
            Sum_func = func([s[0] + 1, s[1]], t) + func([s[0], s[1] + 1], t)
            const = (1.0 + (1.0 / (2.0**(sum(s) + 1)))) / 3.0
            time_val = (-2.0 * const * K(s[0]) * K(s[1]) / (N * Sum_func))**(1.0 / (2.0 + sum(s)))
            return psi(s, time_val)
        else:
            return psi(s, t)

    def evolve(t):
        Sum_func = func([0, 2], t) + func([2, 0], t) + 2.0 * func([1, 1], t)
        time_val = (2.0 * np.pi * N * Sum_func)**(-1.0 / 3.0)
        return (t - time_val) / time_val

    try:
        t_star = brentq(evolve, 0.0, 0.1)
    except Exception:
        t_star = 0.01

    p_02 = func([0, 2], t_star)
    p_20 = func([2, 0], t_star)
    p_11 = func([1, 1], t_star)

    common_denom = 4.0 * np.pi * N * (p_11 + np.sqrt(max(0.0, p_20 * p_02)))
    if common_denom != 0 and p_02 > 0 and p_20 > 0:
        t_y = ((p_02**0.75) / (common_denom * (p_20**0.75)))**(1.0 / 3.0)
        t_x = ((p_20**0.75) / (common_denom * (p_02**0.75)))**(1.0 / 3.0)
    else:
        t_x = t_y = t_star

    kx = np.arange(n, dtype=float)[:, None]
    ky = np.arange(n, dtype=float)[None, :]
    a_t = np.exp(-kx**2 * np.pi**2 * t_x / 2.0) * np.exp(-ky**2 * np.pi**2 * t_y / 2.0) * a

    density = idct2d_matlab(a_t) * (a_t.size / np.prod(scaling))

    x_grid = np.linspace(MIN_XY[0], MAX_XY[0], n)
    y_grid = np.linspace(MIN_XY[1], MAX_XY[1], n)
    X, Y = np.meshgrid(x_grid, y_grid)

    bandwidth = np.sqrt(np.array([t_x, t_y])) * scaling
    return bandwidth, density, X, Y


def compute_density_grid(xp, yp, grid_res=256, mindensity=1e-3):
    data = np.column_stack((xp, yp))
    MIN_XY = [-1.0, -1.0]
    MAX_XY = [1.0, 1.0]

    _, density, X, Y = kde2d(data, n=grid_res, MIN_XY=MIN_XY, MAX_XY=MAX_XY)

    Z_grid = density.copy()

    dist = np.sqrt(X**2 + Y**2)
    Z = np.where(dist <= 1.0, Z_grid, np.nan)
    Z[Z < mindensity] = np.nan

    max_val = np.nanmax(Z)
    if max_val > 0:
        Z = (Z / max_val) * 100.0

    Z[Z < 0.5] = np.nan

    return X, Y, Z


# ---------------------------------------------------------
# Interpolacion e Identificacion de Polos Principales
# ---------------------------------------------------------
def interpolate_density_at(x, y, X, Y, Z):
    if np.isnan(x) or np.isnan(y) or (x**2 + y**2 > 1.0):
        return 0.0

    x_vec = X[0, :]
    y_vec = Y[:, 0]
    Z_clean = np.nan_to_num(Z, nan=0.0)

    try:
        interp = RegularGridInterpolator((y_vec, x_vec), Z_clean, bounds_error=False, fill_value=0.0)
        val = interp([[y, x]])[0]
        return float(val)
    except Exception:
        return 0.0


def create_pole_dict(dipdir, dip, projection="Equal-angle", X=None, Y=None, Z=None, idx=1):
    px, py = f_clar2cart(dipdir, dip, projection=projection)
    px = float(np.atleast_1d(px)[0])
    py = float(np.atleast_1d(py)[0])

    N_arr = f_pole2vnor_v02([px, py], projection=projection)
    normal = N_arr[0]

    dens = 0.0
    if X is not None and Y is not None and Z is not None:
        dens = interpolate_density_at(px, py, X, Y, Z)

    return {
        "id": f"J_{idx}",
        "idx": idx,
        "x": px,
        "y": py,
        "dipdir": float(dipdir),
        "dip": float(dip),
        "density": float(dens),
        "normal": normal,
    }


def find_principal_poles(X, Y, Z, projection="Equal-angle", min_angle_deg=30.0, max_poles=5):
    Z_clean = np.nan_to_num(Z, nan=0.0)

    local_max = (maximum_filter(Z_clean, size=3) == Z_clean) & (Z_clean > 0.5)
    row_indices, col_indices = np.where(local_max)

    if len(row_indices) == 0:
        return []

    peak_candidates = []
    for r, c in zip(row_indices, col_indices):
        px = X[r, c]
        py = Y[r, c]
        dens = Z_clean[r, c]
        peak_candidates.append({"x": px, "y": py, "density": dens})

    peak_candidates.sort(key=lambda item: item["density"], reverse=True)

    poles_cart = np.array([[p["x"], p["y"]] for p in peak_candidates])
    normals_3d = f_pole2vnor_v02(poles_cart, projection=projection)
    dipdir_arr, dip_arr = f_vnorm2clar_v02(normals_3d)

    for idx, p in enumerate(peak_candidates):
        p["normal"] = normals_3d[idx]
        p["dipdir"] = dipdir_arr[idx]
        p["dip"] = dip_arr[idx]

    accepted_poles = []
    for p in peak_candidates:
        N_cand = p["normal"]
        is_valid = True

        for acc in accepted_poles:
            N_acc = acc["normal"]
            dot_prod = np.abs(np.clip(np.dot(N_cand, N_acc), -1.0, 1.0))
            angle_deg = np.arccos(dot_prod) * 180.0 / np.pi

            if angle_deg < min_angle_deg:
                is_valid = False
                break

        if is_valid:
            idx_num = len(accepted_poles) + 1
            p["id"] = f"J_{idx_num}"
            p["idx"] = idx_num
            accepted_poles.append(p)
            if len(accepted_poles) >= max_poles:
                break

    return accepted_poles


def draw_density_from_grid(ax, X, Y, Z, projection="Equal-angle", labeled=1, filled=False, n_levels=80, principal_poles=None):
    ax.clear()

    max_val = np.nanmax(Z)
    if np.isnan(max_val) or max_val <= 0:
        draw_stereonet(ax, projection=projection, labeled=labeled)
        return None

    levels = np.linspace(0.0, 100.0, n_levels + 1)

    if filled:
        cf = ax.contourf(X, Y, Z, levels=levels, cmap="jet", alpha=0.85, extend="neither")
        ax.contour(X, Y, Z, levels=levels, colors="k", linewidths=0.25, alpha=0.3)
    else:
        cf = ax.contour(X, Y, Z, levels=levels, cmap="jet", linewidths=0.7)

    draw_stereonet(ax, projection=projection, labeled=labeled)

    if principal_poles:
        for p in principal_poles:
            px, py = p["x"], p["y"]
            idx_num = p.get("idx", 1)

            ax.plot(px, py, "ro", markersize=5.5, markeredgecolor="black", markeredgewidth=0.8, zorder=10)

            latex_label = f"$J_{{{idx_num}}}$"
            txt = ax.text(
                px + 0.035, py + 0.025, latex_label,
                fontsize=11, fontweight="bold", color="black", zorder=11
            )
            txt.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground="white")])

    def custom_format_coord(x_pos, y_pos):
        dipdir, dip = f_cart2clar(x_pos, y_pos, projection=projection)
        if dipdir is None:
            return _tr("plot.outside_cursor", radius=np.sqrt(x_pos**2 + y_pos**2))
        return _tr("plot.coord_cursor", dipdir=dipdir, dip=dip, projection=projection)

    ax.format_coord = custom_format_coord

    return cf


# ---------------------------------------------------------
# Efficient CloudCompare scalar-field writing
# ---------------------------------------------------------
def write_scalar_field_cpp(cloud, name, values):
    """Create or update a scalar field through ccScalarField.setValue().

    This intentionally uses the stable C++ binding point by point. It is
    slower than a true C++ bulk copy, but it avoids the unreliable writable
    NumPy view observed with some embedded PythonRuntime builds.
    """
    values = np.asarray(values, dtype=np.float32).reshape(-1)
    if values.size != cloud.size():
        raise ValueError(
            f"Scalar field '{name}' has {values.size} values, "
            f"but cloud has {cloud.size()} points."
        )

    sf_idx = cloud.getScalarFieldIndexByName(name)
    if sf_idx < 0:
        sf_idx = cloud.addScalarField(name)
    if sf_idx < 0:
        raise RuntimeError(_tr("error.scalar_field_create", name=name))

    sf = cloud.getScalarField(sf_idx)
    for point_index in range(values.size):
        sf.setValue(point_index, float(values[point_index]))

    sf.computeMinAndMax()
    return sf_idx, sf


def compute_fisher_k_by_family(
        normals, principal_poles, family_ids=None,
        max_cone_angle_deg=None):
    """Compute axial Fisher K, N and R for each principal-pole family."""
    normals = np.asarray(normals, dtype=np.float64)
    if normals.ndim != 2 or normals.shape[1] != 3:
        raise ValueError(_tr("error.normals_shape"))

    lengths = np.linalg.norm(normals, axis=1)
    valid = np.isfinite(normals).all(axis=1) & (lengths > 0.0)
    unit_normals = np.zeros_like(normals)
    unit_normals[valid] = normals[valid] / lengths[valid, None]

    if not principal_poles:
        return {}

    pole_normals = []
    for pole in principal_poles:
        if pole.get("normal") is not None:
            vector = np.asarray(pole["normal"], dtype=np.float64)
        else:
            px, py = f_clar2cart(pole["dipdir"], pole["dip"])
            vector = f_pole2vnor_v02([px, py])[0]
        length = np.linalg.norm(vector)
        if not np.isfinite(length) or length <= 0.0:
            raise ValueError(_tr("error.invalid_pole_normal"))
        pole_normals.append(vector / length)
    pole_normals = np.asarray(pole_normals, dtype=np.float64)

    axial_dots = np.clip(np.abs(unit_normals @ pole_normals.T), 0.0, 1.0)
    if family_ids is None:
        best_indices = np.argmax(axial_dots, axis=1)
        best_dots = axial_dots[np.arange(len(unit_normals)), best_indices]
        family_ids = best_indices + 1
        if max_cone_angle_deg is not None:
            cone_cos = np.cos(np.radians(float(max_cone_angle_deg)))
            family_ids = np.where(best_dots >= cone_cos, family_ids, 0)
    else:
        family_ids = np.asarray(family_ids, dtype=int).reshape(-1)
        if family_ids.size != normals.shape[0]:
            raise ValueError(_tr("error.family_ids_size"))

    results = {}
    for family_index, pole_normal in enumerate(pole_normals, start=1):
        vectors = unit_normals[valid & (family_ids == family_index)].copy()
        count = int(len(vectors))
        if count == 0:
            results[family_index] = {"K": np.nan, "N": 0, "R": 0.0}
            continue

        vectors[(vectors @ pole_normal) < 0.0] *= -1.0
        R = min(float(np.linalg.norm(vectors.sum(axis=0))), float(count))
        if count < 2:
            fisher_k = np.nan
        else:
            denominator = float(count) - R
            tolerance = np.finfo(np.float64).eps * max(count, 1) * 8.0
            fisher_k = np.inf if denominator <= tolerance else (count - 1.0) / denominator
        results[family_index] = {"K": float(fisher_k), "N": count, "R": R}

    return results


def compute_cloud_fisher_k(
        cloud, principal_poles, family_ids=None,
        max_cone_angle_deg=None):
    """Convenience wrapper that reads normals directly from a cloud."""
    if not cloud.hasNormals():
        raise ValueError(_tr("error.cloud_no_normals"))
    normals = np.asarray(cloud.normals(), dtype=np.float64)
    return compute_fisher_k_by_family(
        normals, principal_poles, family_ids=family_ids,
        max_cone_angle_deg=max_cone_angle_deg
    )


# ---------------------------------------------------------
# CLASIFICACION Y ESCRITURA GARANTIZADA DEL ESCALAR 'Discontinuity Set (DS)'
# ---------------------------------------------------------
def classify_point_cloud_js(cloud, principal_poles, max_cone_angle_deg=30.0, progress_callback=None):
    """
    Calcula la asignacion de polo principal para cada punto en un vector 1D (dimension N)
    e inyecta el escalar 'Discontinuity Set (DS)' en la memoria C++ de CloudCompare.
    """
    t_start = time.time()

    def _report(pct, text):
        if progress_callback:
            return progress_callback(pct, text)
        return True

    if not principal_poles or len(principal_poles) == 0:
        return None, _tr("error.no_principal_poles")

    npts = cloud.size()
    if npts == 0:
        return None, _tr("error.point_cloud_empty")

    if not cloud.hasNormals():
        return None, _tr("error.cloud_normals_missing")

    _report(10, _tr("progress.reading_normals", count=npts))

    # 1. Matriz de normales de la nube (N, 3)
    normals = np.asarray(cloud.normals(), dtype=np.float64)
    norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
    norm_len[norm_len == 0] = 1.0
    normals = normals / norm_len

    # 2. Matriz de normales de polos principales (K, 3)
    K = len(principal_poles)
    P_normals = np.zeros((K, 3), dtype=np.float64)

    for k, p in enumerate(principal_poles):
        if "normal" in p and p["normal"] is not None:
            p_vec = np.array(p["normal"], dtype=np.float64)
        else:
            px, py = f_clar2cart(p["dipdir"], p["dip"])
            p_vec = f_pole2vnor_v02([px, py])[0]

        p_len = np.linalg.norm(p_vec)
        if p_len > 0:
            p_vec /= p_len
        P_normals[k] = p_vec

    _report(30, _tr("progress.angular_distance", count=K))

    # 3. Angulos 3D con simetria antipodal |u . v| -> Matriz (N, K)
    dots = normals @ P_normals.T
    abs_dots = np.clip(np.abs(dots), 0.0, 1.0)
    angles_deg = np.degrees(np.arccos(abs_dots))

    # 4. Obtencion del angulo minimo por punto y su correspondiente familia
    min_angles_deg = np.min(angles_deg, axis=1)
    best_pole_idx = np.argmin(angles_deg, axis=1) + 1

    # 5. Vector 1D final de dimension N (JS)
    js_vector = np.where(min_angles_deg <= max_cone_angle_deg, best_pole_idx, 0).astype(np.float32)

    _report(70, _tr("progress.writing_ds"))

    # 6. Crear o recuperar el escalar 'Discontinuity Set (DS)' en CloudCompare
    sf_idx, sf = write_scalar_field_cpp(cloud, "Discontinuity Set (DS)", js_vector)
    cloud.setCurrentScalarField(sf_idx)
    cloud.setCurrentDisplayedScalarField(sf_idx)
    cloud.showSF(True)

    elapsed = time.time() - t_start

    # 8. Reporte detallado del numero de puntos asignados
    unique_vals, counts = np.unique(js_vector, return_counts=True)
    summary_counts = dict(zip(unique_vals.astype(int).tolist(), counts.tolist()))

    log_lines = []
    log_lines.append(_tr("stereo.js_complete", seconds=elapsed))
    log_lines.append(_tr("stereo.total_points", count=npts))
    log_lines.append(_tr("stereo.cone_threshold", value=max_cone_angle_deg))
    log_lines.append(_tr("stereo.family_counts"))

    j0_cnt = summary_counts.get(0, 0)
    log_lines.append(_tr("stereo.j0", count=j0_cnt, percent=(j0_cnt/npts)*100.0))

    for k in range(1, K + 1):
        cnt = summary_counts.get(k, 0)
        pct = (cnt / npts) * 100.0
        log_lines.append(_tr("stereo.family", family=k, count=cnt, percent=pct))

    full_log = "\n".join(log_lines)
    _report(100, full_log)

    return summary_counts, full_log


# ---------------------------------------------------------
# Estimacion de EPS y DBSCAN (Campo 'Cluster id (cl)')
# ---------------------------------------------------------
def compute_family_eps_knn(coords, k_neighbor=4, k_sigma=2.0):
    n_pts = len(coords)
    if n_pts <= 1:
        return 0.1, 0.0, 0.0

    k_query = min(k_neighbor + 1, n_pts)

    tree = cKDTree(coords)
    dists, _ = tree.query(coords, k=k_query)

    if dists.ndim == 1:
        knn_dists = dists
    else:
        knn_dists = dists[:, -1]

    data_unique = np.unique(knn_dists)

    mean_val = float(np.mean(data_unique))
    std_val = float(np.std(data_unique))

    eps = mean_val + k_sigma * std_val
    if np.isnan(eps) or eps <= 0:
        eps = 1e-3

    return eps, mean_val, std_val


def native_dbscan_kdtree(coords, eps, min_samples, progress_callback=None, family_label=""):
    n_points = len(coords)
    labels = np.full(n_points, -1, dtype=int)
    if n_points == 0:
        return labels

    def _check_cancel(pct, text):
        if progress_callback:
            if progress_callback(pct, text) is False:
                raise CalculationCancelledException(_tr("cancel.calculation"))

    _check_cancel(5, _tr("progress.dbscan_tree", family=family_label, count=n_points))
    tree = cKDTree(coords)

    _check_cancel(20, _tr("progress.dbscan_neighbours", family=family_label, count=n_points))
    try:
        counts = np.asarray(tree.query_ball_point(coords, r=eps, return_length=True, workers=-1))
    except TypeError:
        neighbor_lists = tree.query_ball_point(coords, r=eps)
        counts = np.fromiter((len(nb) for nb in neighbor_lists), count=n_points, dtype=int)

    core_mask = counts >= min_samples
    n_core = int(np.count_nonzero(core_mask))

    if n_core == 0:
        _check_cancel(100, _tr("progress.dbscan_no_core", family=family_label))
        return labels

    _check_cancel(40, _tr("progress.dbscan_pairs", family=family_label, count=n_core))
    try:
        pairs = tree.query_pairs(r=eps, output_type="ndarray")
    except TypeError:
        pairs_set = tree.query_pairs(r=eps)
        pairs = np.array(list(pairs_set), dtype=int) if pairs_set else np.empty((0, 2), dtype=int)

    _check_cancel(65, _tr("progress.dbscan_graph", family=family_label))
    core_idx = np.where(core_mask)[0]
    core_lookup = -np.ones(n_points, dtype=int)
    core_lookup[core_idx] = np.arange(n_core)

    if len(pairs) > 0:
        a, b = pairs[:, 0], pairs[:, 1]
        both_core = core_mask[a] & core_mask[b]
        ca = core_lookup[a[both_core]]
        cb = core_lookup[b[both_core]]
    else:
        ca = np.array([], dtype=int)
        cb = np.array([], dtype=int)

    graph = coo_matrix((np.ones(len(ca)), (ca, cb)), shape=(n_core, n_core))
    _, comp_labels = connected_components(graph, directed=False)
    labels[core_idx] = comp_labels

    _check_cancel(85, _tr("progress.dbscan_border", family=family_label))
    border_idx = np.where(~core_mask)[0]
    if len(border_idx) > 0 and len(pairs) > 0:
        a, b = pairs[:, 0], pairs[:, 1]
        a_core = core_mask[a]
        b_core = core_mask[b]

        mask1 = (~a_core) & b_core
        mask2 = a_core & (~b_core)

        border_pts = np.concatenate([a[mask1], b[mask2]])
        assoc_core = np.concatenate([b[mask1], a[mask2]])
        assoc_cluster = comp_labels[core_lookup[assoc_core]]

        order = np.argsort(border_pts, kind="stable")
        border_pts_sorted = border_pts[order]
        assoc_cluster_sorted = assoc_cluster[order]
        _, first_idx = np.unique(border_pts_sorted, return_index=True)
        labels[border_pts_sorted[first_idx]] = assoc_cluster_sorted[first_idx]

    _check_cancel(100, _tr("progress.dbscan_finished", family=family_label))
    return labels


def run_dbscan_clustering_by_family(cloud, k_neighbor=4, k_sigma=2.0, min_samples=4, progress_callback=None):
    sf_js_idx = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    if sf_js_idx < 0:
        return None, _tr("error.ds_field_missing_classify")

    npts = cloud.size()
    if npts == 0:
        return None, _tr("error.point_cloud_empty")

    if progress_callback:
        if progress_callback(0, _tr("progress.reading_coords_ds")) is False:
            return None, _tr("cancel.user")

    try:
        coords = cloud.points()
        if coords is None or len(coords) != npts:
            return None, _tr("error.coordinates_unavailable")

        sf_js = cloud.getScalarField(sf_js_idx)
        js_vals = np.array(sf_js.asArray(), dtype=int)

        cl_values = np.zeros(npts, dtype=np.float32)
        family_stats = {}

        unique_families = np.unique(js_vals)
        unique_families = unique_families[unique_families > 0]

        if len(unique_families) == 0:
            return None, _tr("error.no_valid_families")

        num_families = len(unique_families)

        for fam_idx, family_id in enumerate(unique_families):
            mask = (js_vals == family_id)
            indices = np.where(mask)[0]
            fam_coords = coords[mask]

            family_label = f"Family J_{family_id} ({fam_idx + 1}/{num_families})"

            if len(fam_coords) < min_samples:
                family_stats[family_id] = {
                    "clusters": 0, "pts": len(fam_coords),
                    "noise": len(fam_coords), "eps": 0.0, "mean": 0.0, "std": 0.0
                }
                continue

            eps, mean_val, std_val = compute_family_eps_knn(fam_coords, k_neighbor=k_neighbor, k_sigma=k_sigma)

            def family_sub_cb(sub_pct, text):
                if progress_callback:
                    overall_pct = int(((fam_idx + (sub_pct / 100.0)) / num_families) * 100)
                    return progress_callback(overall_pct, text)
                return True

            labels = native_dbscan_kdtree(
                fam_coords, eps=eps, min_samples=min_samples,
                progress_callback=family_sub_cb, family_label=family_label
            )

            valid_mask = labels >= 0
            if np.any(valid_mask):
                unique_cls, cls_counts = np.unique(labels[valid_mask], return_counts=True)
                order = np.argsort(-cls_counts)  # descending by size
                remap = np.zeros(int(unique_cls.max()) + 1, dtype=int)
                for new_id, old_id in enumerate(unique_cls[order], start=1):
                    remap[int(old_id)] = new_id
                remapped = np.where(valid_mask, remap[labels], -1)
            else:
                remapped = labels

            cluster_ids = np.where(remapped >= 0, remapped, 0)
            cl_values[indices] = cluster_ids.astype(np.float32)

            n_clusters = int(np.any(valid_mask) and len(unique_cls))
            n_noise = np.sum(labels == -1)

            family_stats[family_id] = {
                "clusters": n_clusters,
                "pts": len(fam_coords),
                "noise": n_noise,
                "eps": eps,
                "mean": mean_val,
                "std": std_val
            }

        if progress_callback:
            if progress_callback(98, _tr("progress.writing_cl")) is False:
                return None, _tr("cancel.user")

        sf_cl_idx, sf_cl = write_scalar_field_cpp(cloud, "Cluster id (cl)", cl_values)
        cloud.setCurrentScalarField(sf_cl_idx)
        cloud.setCurrentDisplayedScalarField(sf_cl_idx)
        cloud.showSF(True)

        if progress_callback:
            progress_callback(100, _tr("progress.dbscan_complete"))

        return family_stats, "Success"

    except CalculationCancelledException:
        return None, _tr("cancel.user")

# ---------------------------------------------------------
# Calculo del Plano de Mejor Ajuste por Cluster
# ---------------------------------------------------------
# ---------------------------------------------------------
# Calculo del Plano de Mejor Ajuste por Cluster
# ---------------------------------------------------------
def compute_cluster_planes(
        cloud, principal_poles, fix_orientation=True, sort_by="size",
        random_seed=None, progress_callback=None, write_scalars=True):
    def _report(pct, text):
        if progress_callback:
            cont = progress_callback(pct, text)
            if cont is False:
                raise CalculationCancelledException(_tr("cancel.user"))

    sf_js_idx = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    sf_cl_idx = cloud.getScalarFieldIndexByName("Cluster id (cl)")
    if sf_js_idx < 0:
        return None, _tr("error.ds_field_missing")
    if sf_cl_idx < 0:
        return None, _tr("error.cl_field_missing")

    npts = cloud.size()
    _report(2, _tr("progress.reading_coordinates", count=npts))
    coords = np.asarray(cloud.points(), dtype=np.float64)
    js_vals = np.array(cloud.getScalarField(sf_js_idx).asArray(), dtype=int)
    cl_vals = np.array(cloud.getScalarField(sf_cl_idx).asArray(), dtype=int)

    results = {}
    n_families = len(principal_poles)

    try:
        for fam_num, p in enumerate(principal_poles):
            family_id = p.get("idx", fam_num + 1)
            _report(
                5 + int(40 * fam_num / max(n_families, 1)),
                _tr("progress.fitting_planes_family", family=family_id, position=fam_num + 1, total=n_families)
            )

            fam_mask = (js_vals == family_id)
            if not np.any(fam_mask):
                continue

            fam_cl = cl_vals[fam_mask]
            fam_coords = coords[fam_mask]
            unique_clusters = np.unique(fam_cl[fam_cl > 0])

            if fix_orientation:
                pole_normal = np.array(p["normal"], dtype=np.float64)
                pole_normal /= np.linalg.norm(pole_normal)

            family_planes = {}
            for cl_id in unique_clusters:
                pts = fam_coords[fam_cl == cl_id]
                if len(pts) < 3:
                    continue
                centroid = pts.mean(axis=0)
                if fix_orientation:
                    normal = pole_normal.copy()
                else:
                    _, _, Vt = np.linalg.svd(pts - centroid, full_matrices=False)
                    normal = Vt[-1]
                    if normal[2] < 0:
                        normal = -normal
                D = -float(np.dot(normal, centroid))
                dipdir_arr, dip_arr = f_vnorm2clar_v02(normal.reshape(1, 3))
                family_planes[int(cl_id)] = {
                    "normal": tuple(normal), "D": D,
                    "dipdir": float(dipdir_arr[0]), "dip": float(dip_arr[0]),
                    "centroid": tuple(centroid), "n_pts": len(pts),
                }

            ordered = None
            if sort_by == "D" and fix_orientation and family_planes:
                ordered = sorted(family_planes.items(), key=lambda x: x[1]["D"])
            elif sort_by == "random" and family_planes:
                ordered = list(family_planes.items())
                family_seed = None if random_seed is None else int(random_seed) + int(family_id)
                np.random.default_rng(family_seed).shuffle(ordered)
            if ordered is not None:
                remap = {old_id: new_id for new_id, (old_id, _) in enumerate(ordered, start=1)}
                family_planes = {remap[oid]: info for oid, info in family_planes.items()}
                fam_indices = np.where(fam_mask)[0]
                for idx in fam_indices:
                    if cl_vals[idx] in remap:
                        cl_vals[idx] = remap[cl_vals[idx]]

            results[family_id] = family_planes

        if (sort_by == "D" and fix_orientation) or sort_by == "random":
            _report(48, _tr("progress.rewriting_cl"))
            sf_cl_idx, sf_cl = write_scalar_field_cpp(cloud, "Cluster id (cl)", cl_vals)

        if not write_scalars:
            _report(100, _tr("progress.plane_calc_deferred"))
            return results, "Success"

        _report(52, _tr("progress.building_plane_arrays"))
        A_vals = np.zeros(npts, dtype=np.float32)
        B_vals = np.zeros(npts, dtype=np.float32)
        C_vals = np.zeros(npts, dtype=np.float32)
        D_vals = np.zeros(npts, dtype=np.float32)

        for family_id, family_planes in results.items():
            fam_mask = (js_vals == family_id)
            for cl_id, info in family_planes.items():
                mask = fam_mask & (cl_vals == cl_id)
                A, B, C = info["normal"]
                A_vals[mask] = float(A)
                B_vals[mask] = float(B)
                C_vals[mask] = float(C)
                D_vals[mask] = float(info["D"])

        _report(58, _tr("progress.writing_plane_scalars", count=npts))

        scalar_arrays = {"A": A_vals, "B": B_vals, "C": C_vals, "D": D_vals}
        for field_pos, (name, values) in enumerate(scalar_arrays.items(), start=1):
            _report(58 + int(38 * field_pos / len(scalar_arrays)),
                    _tr("progress.writing_scalar_field", name=name, position=field_pos, total=4))
            write_scalar_field_cpp(cloud, name, values)

        cl_final_idx = cloud.getScalarFieldIndexByName("Cluster id (cl)")
        cloud.setCurrentScalarField(cl_final_idx)
        cloud.setCurrentDisplayedScalarField(cl_final_idx)
        cloud.showSF(True)

        _report(100, _tr("progress.plane_calc_complete"))
        return results, "Success"

    except CalculationCancelledException:
        return None, _tr("cancel.user")

# ---------------------------------------------------------
# Coplanarity merge for clusters with a shared family normal
# ---------------------------------------------------------
def merge_coplanar_clusters(
        cloud, cluster_planes, k_sigmas=1.5, fix_orientation=True,
        sort_by="size", random_seed=None, progress_callback=None):
    """Merge same-family clusters using the DSE sigma-overlap test."""
    def _report(pct, text):
        if progress_callback and progress_callback(pct, text) is False:
            raise CalculationCancelledException(_tr("cancel.user"))

    if k_sigmas <= 0.0:
        return cluster_planes, {}, _tr("stereo.coplanarity_disabled")
    if not fix_orientation:
        return cluster_planes, {}, _tr("stereo.coplanarity_requires_orientation")

    sf_js_idx = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    sf_cl_idx = cloud.getScalarFieldIndexByName("Cluster id (cl)")
    if sf_js_idx < 0 or sf_cl_idx < 0:
        return None, {}, _tr("error.js_cl_fields_missing")

    npts = cloud.size()
    coords = np.asarray(cloud.points(), dtype=np.float64)
    js_vals = np.asarray(cloud.getScalarField(sf_js_idx).asArray(), dtype=int)
    cl_vals = np.asarray(cloud.getScalarField(sf_cl_idx).asArray(), dtype=int).copy()
    merged_results = {}
    merge_stats = {}
    family_ids = sorted(cluster_planes.keys())

    try:
        for fam_pos, family_id in enumerate(family_ids):
            family_planes = cluster_planes.get(family_id, {})
            old_ids = sorted(family_planes.keys())
            n_clusters = len(old_ids)
            _report(5 + int(65 * fam_pos / max(len(family_ids), 1)),
                    _tr("progress.testing_coplanarity", family=family_id, count=n_clusters))
            if n_clusters == 0:
                merged_results[family_id] = {}
                merge_stats[family_id] = {"before": 0, "after": 0, "merged": 0}
                continue

            sigmas = np.zeros(n_clusters, dtype=np.float64)
            offsets = np.zeros(n_clusters, dtype=np.float64)
            for pos, cl_id in enumerate(old_ids):
                info = family_planes[cl_id]
                normal = np.asarray(info["normal"], dtype=np.float64)
                normal /= max(np.linalg.norm(normal), np.finfo(float).eps)
                D = float(info["D"])
                pts = coords[(js_vals == family_id) & (cl_vals == cl_id)]
                residuals = pts @ normal + D
                sigmas[pos] = np.sqrt(np.sum(residuals * residuals) / (len(pts) - 1)) if len(pts) > 1 else 0.0
                offsets[pos] = D

            if n_clusters == 1:
                labels = np.zeros(1, dtype=int)
            else:
                delta_d = np.abs(offsets[:, None] - offsets[None, :])
                sigma_sum = sigmas[:, None] + sigmas[None, :]
                ratio = np.full_like(delta_d, np.inf)
                positive = sigma_sum > np.finfo(float).eps
                ratio[positive] = delta_d[positive] / sigma_sum[positive]
                ratio[(~positive) & (delta_d <= np.finfo(float).eps)] = 0.0
                adjacency = ratio <= float(k_sigmas)
                np.fill_diagonal(adjacency, True)
                _, labels = connected_components(
                    coo_matrix(adjacency.astype(np.uint8)), directed=False,
                    return_labels=True
                )

            components = []
            for component_id in np.unique(labels):
                members = [old_ids[i] for i in np.where(labels == component_id)[0]]
                mask = (js_vals == family_id) & np.isin(cl_vals, members)
                components.append((members, mask, int(np.count_nonzero(mask))))
            if sort_by == "D":
                components.sort(key=lambda item: float(np.mean(
                    offsets[[old_ids.index(v) for v in item[0]]])))
            elif sort_by == "random":
                family_seed = None if random_seed is None else int(random_seed) + int(family_id)
                rng = np.random.default_rng(family_seed)
                rng.shuffle(components)
            else:
                components.sort(key=lambda item: (-item[2], min(item[0])))

            new_family = {}
            for new_id, (members, mask, count) in enumerate(components, start=1):
                pts = coords[mask]
                normal = np.asarray(family_planes[members[0]]["normal"], dtype=np.float64)
                normal /= max(np.linalg.norm(normal), np.finfo(float).eps)
                centroid = pts.mean(axis=0)
                D = -float(np.dot(normal, centroid))
                residuals = pts @ normal + D
                sigma = float(np.sqrt(np.sum(residuals * residuals) / (count - 1))) if count > 1 else 0.0
                dipdir_arr, dip_arr = f_vnorm2clar_v02(normal.reshape(1, 3))
                new_family[new_id] = {
                    "normal": tuple(normal), "D": D,
                    "dipdir": float(dipdir_arr[0]), "dip": float(dip_arr[0]),
                    "centroid": tuple(centroid), "n_pts": count,
                    "sigma": sigma, "source_clusters": tuple(members),
                }
                cl_vals[mask] = new_id
            merged_results[family_id] = new_family
            after = len(new_family)
            merge_stats[family_id] = {
                "before": n_clusters, "after": after,
                "merged": n_clusters - after,
            }

        # Final defensive compaction after all merge operations.
        # Each family receives consecutive cluster IDs in the range 1..N.
        # Noise remains 0. This also removes any gaps left by future merge
        # strategies or by non-consecutive source cluster identifiers.
        for family_id in sorted(merged_results.keys()):
            family_planes = merged_results[family_id]
            family_mask = (js_vals == family_id)
            old_ids = sorted(
                int(value) for value in np.unique(cl_vals[family_mask])
                if int(value) > 0 and int(value) in family_planes
            )
            compact_map = {old_id: new_id for new_id, old_id in enumerate(old_ids, start=1)}
            if not compact_map:
                merged_results[family_id] = {}
                merge_stats[family_id]["after"] = 0
                merge_stats[family_id]["id_min"] = 0
                merge_stats[family_id]["id_max"] = 0
                continue

            old_family_values = cl_vals[family_mask].copy()
            compact_values = np.zeros_like(old_family_values)
            for old_id, new_id in compact_map.items():
                compact_values[old_family_values == old_id] = new_id
            cl_vals[family_mask] = compact_values

            compact_planes = {}
            for old_id, new_id in compact_map.items():
                info = family_planes[old_id]
                info["cluster_id"] = new_id
                compact_planes[new_id] = info
            merged_results[family_id] = compact_planes

            final_count = len(compact_planes)
            merge_stats[family_id]["after"] = final_count
            merge_stats[family_id]["merged"] = (
                merge_stats[family_id]["before"] - final_count
            )
            merge_stats[family_id]["id_min"] = 1
            merge_stats[family_id]["id_max"] = final_count

        arrays = {
            "Cluster id (cl)": cl_vals.astype(np.float32),
            "A": np.zeros(npts, dtype=np.float32),
            "B": np.zeros(npts, dtype=np.float32),
            "C": np.zeros(npts, dtype=np.float32),
            "D": np.zeros(npts, dtype=np.float32),
            "sigma": np.zeros(npts, dtype=np.float32),
        }
        for family_id, family_planes in merged_results.items():
            for cl_id, info in family_planes.items():
                mask = (js_vals == family_id) & (cl_vals == cl_id)
                arrays["A"][mask], arrays["B"][mask], arrays["C"][mask] = info["normal"]
                arrays["D"][mask] = info["D"]
                arrays["sigma"][mask] = info["sigma"]

        for field_pos, (name, values) in enumerate(arrays.items(), start=1):
            _report(72 + int(26 * field_pos / len(arrays)),
                    _tr("progress.writing_merged_scalar", name=name, position=field_pos, total=len(arrays)))
            write_scalar_field_cpp(cloud, name, values)

        sf_cl_idx = cloud.getScalarFieldIndexByName("Cluster id (cl)")
        cloud.setCurrentScalarField(sf_cl_idx)
        cloud.setCurrentDisplayedScalarField(sf_cl_idx)
        cloud.showSF(True)
        _report(100, _tr("progress.coplanarity_complete"))
        return merged_results, merge_stats, "Success"
    except CalculationCancelledException:
        return None, {}, _tr("cancel.user")


# ---------------------------------------------------------
# Cluster facet geometry
# ---------------------------------------------------------
def compute_cluster_convex_facet(points, normal, facet_type="convex"):
    """Project a cluster to its plane and return a selected planar boundary.

    ``facet_type`` accepts ``convex``, ``disk``, ``ellipse`` and ``rectangle``.
    The disk is centred at the cluster centroid and encloses every projected
    point. The ellipse and rectangle use PCA axes and their projected extents.
    """
    points = np.asarray(points, dtype=np.float64)
    normal = np.asarray(normal, dtype=np.float64).reshape(3)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        return None, _tr("error.three_points_required")
    n_len = np.linalg.norm(normal)
    if not np.isfinite(n_len) or n_len <= np.finfo(float).eps:
        return None, _tr("error.invalid_plane_normal")
    normal = normal / n_len
    centroid = points.mean(axis=0)
    reference = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(np.dot(normal, reference))) > 0.9:
        reference = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    axis_u = np.cross(reference, normal)
    u_len = np.linalg.norm(axis_u)
    if u_len <= np.finfo(float).eps:
        return None, _tr("error.local_plane_basis")
    axis_u /= u_len
    axis_v = np.cross(normal, axis_u)
    axis_v /= np.linalg.norm(axis_v)
    centered = points - centroid
    points_2d = np.column_stack((centered @ axis_u, centered @ axis_v))
    unique_2d = np.unique(points_2d, axis=0)
    if len(unique_2d) < 3:
        return None, _tr("error.projected_degenerate")

    facet_type = str(facet_type).lower()
    if facet_type == "convex":
        try:
            hull = ConvexHull(unique_2d)
        except QhullError:
            return None, _tr("error.projected_collinear")
        boundary_2d = unique_2d[hull.vertices]
        area = float(hull.volume)
        perimeter = float(hull.area)
    elif facet_type == "disk":
        radius = float(np.max(np.linalg.norm(points_2d, axis=1)))
        if radius <= np.finfo(float).eps:
            return None, _tr("error.projected_zero_extent")
        angles = np.linspace(0.0, 2.0 * np.pi, 64, endpoint=False)
        boundary_2d = radius * np.column_stack((np.cos(angles), np.sin(angles)))
        area = float(np.pi * radius ** 2)
        perimeter = float(2.0 * np.pi * radius)
    elif facet_type in ("ellipse", "rectangle"):
        _, _, right_vectors = np.linalg.svd(points_2d, full_matrices=False)
        principal_axes = right_vectors[:2]
        local_points = points_2d @ principal_axes.T
        half_axes = np.max(np.abs(local_points), axis=0)
        if np.any(half_axes <= np.finfo(float).eps):
            return None, _tr("error.projected_collinear")
        if facet_type == "ellipse":
            radial_extent = np.sqrt(np.sum(
                (local_points / half_axes) ** 2, axis=1
            ))
            half_axes *= max(1.0, float(np.max(radial_extent)))
            angles = np.linspace(0.0, 2.0 * np.pi, 64, endpoint=False)
            local_boundary = np.column_stack((
                half_axes[0] * np.cos(angles),
                half_axes[1] * np.sin(angles),
            ))
            area = float(np.pi * half_axes[0] * half_axes[1])
            perimeter = float(np.pi * (
                3.0 * (half_axes[0] + half_axes[1]) - np.sqrt(
                    (3.0 * half_axes[0] + half_axes[1]) *
                    (half_axes[0] + 3.0 * half_axes[1])
                )
            ))
        else:
            local_boundary = np.array([
                [-half_axes[0], -half_axes[1]],
                [half_axes[0], -half_axes[1]],
                [half_axes[0], half_axes[1]],
                [-half_axes[0], half_axes[1]],
            ])
            area = float(4.0 * half_axes[0] * half_axes[1])
            perimeter = float(4.0 * (half_axes[0] + half_axes[1]))
        boundary_2d = local_boundary @ principal_axes
    else:
        return None, _tr("error.unknown_facet_type", facet_type=facet_type)

    if len(boundary_2d) < 3:
        return None, _tr("error.facet_vertices")
    boundary_3d = (centroid + boundary_2d[:, 0, None] * axis_u
                   + boundary_2d[:, 1, None] * axis_v)
    triangles = np.array(
        [[0, i, i + 1] for i in range(1, len(boundary_3d) - 1)],
        dtype=np.int32
    )
    return {
        "vertices": boundary_3d,
        "triangles": triangles,
        "centroid": centroid,
        "normal": normal,
        "area": area,
        "perimeter": perimeter,
        "type": facet_type,
    }, "Success"


# ---------------------------------------------------------
# DSE cluster analysis rebuilt with explicit global indices
# ---------------------------------------------------------
def _dse_eps(points, k_neighbor=4, k_sigma=2.0):
    n = len(points)
    if n <= 1:
        return 1.0e-3, 0.0, 0.0
    k_query = min(int(k_neighbor) + 1, n)
    distances, _ = cKDTree(points).query(points, k=k_query)
    data = distances if distances.ndim == 1 else distances[:, -1]
    data = np.unique(np.asarray(data, dtype=np.float64))
    mean_value = float(np.mean(data))
    std_value = float(np.std(data, ddof=0))
    eps = mean_value + float(k_sigma) * std_value
    if not np.isfinite(eps) or eps <= 0.0:
        eps = 1.0e-3
    return float(eps), mean_value, std_value


def _filter_and_order_dbscan(labels, minimum_cluster_size):
    """Convert -1/0-based labels to DSE 0/noise and 1..N by size."""
    labels = np.asarray(labels, dtype=np.int64)
    output = np.zeros(labels.size, dtype=np.int32)
    positive = labels[labels >= 0]
    if positive.size == 0:
        return output, 0, int(np.count_nonzero(labels < 0)), 0, 0
    ids, counts = np.unique(positive, return_counts=True)
    valid = counts >= int(minimum_cluster_size)
    valid_ids = ids[valid]
    valid_counts = counts[valid]
    order = np.argsort(-valid_counts, kind="stable")
    for new_id, old_id in enumerate(valid_ids[order], start=1):
        output[labels == old_id] = new_id
    rejected_points = int(np.sum(counts[~valid]))
    return output, len(valid_ids), int(np.count_nonzero(labels < 0)), int(np.count_nonzero(~valid)), rejected_points


def run_dse_cluster_analysis(
        cloud, principal_poles, k_neighbor=4, k_sigma=2.0,
        dbscan_minpts=4, minimum_cluster_size=100,
        fix_orientation=True, merge_k_sigmas=1.5,
        sort_by="size", random_seed=None, progress_callback=None):
    """Complete DSE clustering with global point indices as source of truth."""
    def report(percent, text):
        if progress_callback and progress_callback(percent, text) is False:
            raise CalculationCancelledException(_tr("cancel.user"))

    npts = cloud.size()
    if npts == 0:
        return None, None, _tr("error.point_cloud_empty")
    js_index = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    if js_index < 0:
        return None, None, _tr("error.ds_field_missing")
    coordinates = np.asarray(cloud.points(), dtype=np.float64)
    js_values = np.asarray(cloud.getScalarField(js_index).asArray(), dtype=np.int32).copy()
    global_point_ids = np.arange(npts, dtype=np.int64)
    family_ids = [int(v) for v in np.unique(js_values) if int(v) > 0]
    pole_map = {int(p.get("idx", i + 1)): p for i, p in enumerate(principal_poles)}
    family_records = {}
    diagnostics = {}

    try:
        # Phase 1: DBSCAN and ppcluster filtering.
        for family_position, family_id in enumerate(family_ids):
            report(int(45 * family_position / max(len(family_ids), 1)),
                   _tr("progress.clustering_family", family=family_id))
            family_global = global_point_ids[js_values == family_id]
            family_points = coordinates[family_global]
            eps, mean_knn, std_knn = _dse_eps(family_points, k_neighbor, k_sigma)
            raw = native_dbscan_kdtree(
                family_points, eps, int(dbscan_minpts),
                progress_callback=None, family_label=f"J_{family_id}"
            )
            local_final, valid_count, raw_noise, rejected_clusters, rejected_points = (
                _filter_and_order_dbscan(raw, minimum_cluster_size)
            )
            clusters = []
            for cluster_id in range(1, valid_count + 1):
                local_ids = np.flatnonzero(local_final == cluster_id)
                cluster_global = family_global[local_ids].copy()
                clusters.append({
                    "family_id": family_id,
                    "cluster_id": cluster_id,
                    "global_indices": cluster_global,
                })
            valid_points = int(sum(len(c["global_indices"]) for c in clusters))
            zero_points = int(np.count_nonzero(local_final == 0))
            if valid_points + zero_points != len(family_global):
                raise RuntimeError(_tr("error.index_coverage", family=family_id))
            family_records[family_id] = clusters
            diagnostics[family_id] = {
                "pts": len(family_global), "eps": eps,
                "mean": mean_knn, "std": std_knn,
                "raw_noise": raw_noise,
                "rejected_clusters": rejected_clusters,
                "rejected_points": rejected_points,
                "clusters_before_merge": valid_count,
                "clustered_before_merge": valid_points,
                "zero_points": zero_points,
            }

        # Phase 2: fit initial planes from stored global indices.
        report(48, _tr("progress.fitting_cluster_planes"))
        for family_id, clusters in family_records.items():
            pole = pole_map.get(family_id)
            if pole is None:
                raise RuntimeError(_tr("error.no_principal_pole_family", family=family_id))
            pole_normal = np.asarray(pole["normal"], dtype=np.float64)
            pole_normal /= np.linalg.norm(pole_normal)
            for cluster in clusters:
                pts = coordinates[cluster["global_indices"]]
                centroid = pts.mean(axis=0)
                _, _, vt = np.linalg.svd(pts - centroid, full_matrices=False)
                best_fit_normal = vt[-1]
                if best_fit_normal @ pole_normal < 0.0:
                    best_fit_normal = -best_fit_normal
                best_fit_normal /= np.linalg.norm(best_fit_normal)
                fixed_normal = pole_normal.copy()
                fixed_D = -float(fixed_normal @ centroid)
                fixed_residuals = pts @ fixed_normal + fixed_D
                fixed_sigma = float(np.sqrt(
                    np.sum(fixed_residuals ** 2) / max(len(pts) - 1, 1)
                ))
                free_D = -float(best_fit_normal @ centroid)
                free_residuals = pts @ best_fit_normal + free_D
                free_sigma = float(np.sqrt(
                    np.sum(free_residuals ** 2) / max(len(pts) - 1, 1)
                ))
                if fix_orientation:
                    normal, D, sigma = fixed_normal, fixed_D, fixed_sigma
                else:
                    normal, D, sigma = best_fit_normal.copy(), free_D, free_sigma
                normal /= np.linalg.norm(normal)
                cluster.update({"normal": normal, "centroid": centroid, "D": D,
                                "sigma": sigma, "n_pts": len(pts),
                                "fixed_normal": fixed_normal,
                                "fixed_D": fixed_D, "fixed_sigma": fixed_sigma,
                                "free_normal": best_fit_normal,
                                "free_D": free_D, "free_sigma": free_sigma,
                                "best_fit_normal": best_fit_normal})

        # Save immutable pre-merge cluster data for roughness auditing.
        raw_arrays = {name: np.zeros(npts, dtype=np.float32) for name in (
            "Raw cluster id (cl_raw)", "A_raw", "B_raw", "C_raw", "D_raw"
        )}
        for family_id, clusters in family_records.items():
            for cluster in clusters:
                ids = cluster["global_indices"]
                normal = cluster["free_normal"]
                raw_arrays["Raw cluster id (cl_raw)"][ids] = cluster["cluster_id"]
                raw_arrays["A_raw"][ids] = normal[0]
                raw_arrays["B_raw"][ids] = normal[1]
                raw_arrays["C_raw"][ids] = normal[2]
                raw_arrays["D_raw"][ids] = cluster["free_D"]
        for raw_name, raw_values in raw_arrays.items():
            write_scalar_field_cpp(cloud, raw_name, raw_values)

        # Phase 3: coplanarity merge by connected components of cluster records.
        report(55, _tr("progress.merging_coplanar"))
        if fix_orientation and float(merge_k_sigmas) > 0.0:
            for family_id, clusters in list(family_records.items()):
                count = len(clusters)
                if count <= 1:
                    continue
                offsets = np.array([c["D"] for c in clusters], dtype=float)
                sigmas = np.array([c["sigma"] for c in clusters], dtype=float)
                denominator = sigmas[:, None] + sigmas[None, :]
                separation = np.abs(offsets[:, None] - offsets[None, :])
                ratio = np.full_like(separation, np.inf)
                positive = denominator > np.finfo(float).eps
                ratio[positive] = separation[positive] / denominator[positive]
                ratio[(~positive) & (separation <= np.finfo(float).eps)] = 0.0
                adjacency = ratio <= float(merge_k_sigmas)
                np.fill_diagonal(adjacency, True)
                _, labels = connected_components(
                    coo_matrix(adjacency.astype(np.uint8)), directed=False,
                    return_labels=True
                )
                merged = []
                for component in np.unique(labels):
                    members = [clusters[i] for i in np.flatnonzero(labels == component)]
                    indices = np.unique(np.concatenate([m["global_indices"] for m in members]))
                    pts = coordinates[indices]
                    centroid = pts.mean(axis=0)
                    _, _, vt = np.linalg.svd(pts - centroid, full_matrices=False)
                    best_fit_normal = vt[-1]
                    fixed_normal = members[0]["fixed_normal"].copy()
                    if best_fit_normal @ fixed_normal < 0.0:
                        best_fit_normal = -best_fit_normal
                    best_fit_normal /= np.linalg.norm(best_fit_normal)
                    fixed_D = -float(fixed_normal @ centroid)
                    fixed_residuals = pts @ fixed_normal + fixed_D
                    fixed_sigma = float(np.sqrt(
                        np.sum(fixed_residuals ** 2) / max(len(pts) - 1, 1)
                    ))
                    free_D = -float(best_fit_normal @ centroid)
                    free_residuals = pts @ best_fit_normal + free_D
                    free_sigma = float(np.sqrt(
                        np.sum(free_residuals ** 2) / max(len(pts) - 1, 1)
                    ))
                    normal, D, sigma = fixed_normal, fixed_D, fixed_sigma
                    merged.append({"family_id": family_id, "global_indices": indices,
                                   "normal": normal, "centroid": centroid, "D": D,
                                   "sigma": sigma, "n_pts": len(indices),
                                   "fixed_normal": fixed_normal,
                                   "fixed_D": fixed_D, "fixed_sigma": fixed_sigma,
                                   "free_normal": best_fit_normal,
                                   "free_D": free_D, "free_sigma": free_sigma,
                                   "best_fit_normal": best_fit_normal})
                family_records[family_id] = merged

        # Phase 4: final ordering and consecutive IDs per family.
        for family_id, clusters in family_records.items():
            if sort_by == "D":
                clusters.sort(key=lambda c: c["D"])
            elif sort_by == "random":
                seed = None if random_seed is None else int(random_seed) + family_id
                np.random.default_rng(seed).shuffle(clusters)
            else:
                clusters.sort(key=lambda c: -c["n_pts"])
            for cluster_id, cluster in enumerate(clusters, start=1):
                cluster["cluster_id"] = cluster_id
            diagnostics[family_id]["clusters_after_merge"] = len(clusters)
            diagnostics[family_id]["clustered_after_merge"] = int(
                sum(c["n_pts"] for c in clusters)
            )
            if diagnostics[family_id]["clustered_after_merge"] != diagnostics[family_id]["clustered_before_merge"]:
                raise RuntimeError(_tr("error.merge_coverage", family=family_id))

        # Phase 5: export directly from global indices.
        report(65, _tr("progress.building_final_scalars"))
        arrays = {name: np.zeros(npts, dtype=np.float32)
                  for name in ("Cluster id (cl)", "A", "B", "C", "D", "sigma")}
        assignment_count = np.zeros(npts, dtype=np.uint16)
        results = {}
        for family_id, clusters in family_records.items():
            results[family_id] = {}
            for cluster in clusters:
                ids = cluster["global_indices"]
                assignment_count[ids] += 1
                cid = cluster["cluster_id"]
                normal = cluster["normal"]
                arrays["Cluster id (cl)"][ids] = cid
                arrays["A"][ids] = normal[0]
                arrays["B"][ids] = normal[1]
                arrays["C"][ids] = normal[2]
                arrays["D"][ids] = cluster["D"]
                arrays["sigma"][ids] = cluster["sigma"]
                dipdir, dip = f_vnorm2clar_v02(normal.reshape(1, 3))
                best_fit_normal = cluster["free_normal"]
                fit_dipdir, fit_dip = f_vnorm2clar_v02(
                    best_fit_normal.reshape(1, 3)
                )
                results[family_id][cid] = {
                    "normal": tuple(normal), "D": cluster["D"],
                    "dipdir": float(dipdir[0]), "dip": float(dip[0]),
                    "best_fit_normal": tuple(best_fit_normal),
                    "best_fit_dipdir": float(fit_dipdir[0]),
                    "best_fit_dip": float(fit_dip[0]),
                    "fixed_normal": tuple(cluster["fixed_normal"]),
                    "fixed_D": cluster["fixed_D"],
                    "fixed_sigma": cluster["fixed_sigma"],
                    "free_normal": tuple(cluster["free_normal"]),
                    "free_D": cluster["free_D"],
                    "free_sigma": cluster["free_sigma"],
                    "centroid": tuple(cluster["centroid"]),
                    "n_pts": cluster["n_pts"], "sigma": cluster["sigma"],
                    "global_indices": ids.copy(),
                }
        if np.any(assignment_count > 1):
            raise RuntimeError(_tr("error.duplicate_assignments"))
        for family_id, clusters in family_records.items():
            expected = np.unique(np.concatenate([c["global_indices"] for c in clusters])) if clusters else np.array([], dtype=int)
            if expected.size and not np.all(assignment_count[expected] == 1):
                raise RuntimeError(_tr("error.missing_assignments", family=family_id))

        for position, name in enumerate(("Cluster id (cl)", "A", "B", "C", "D", "sigma"), start=1):
            report(68 + int(30 * position / 6), _tr("progress.writing_scalar_field", name=name, position=position, total=6))
            write_scalar_field_cpp(cloud, name, arrays[name])
        cl_index = cloud.getScalarFieldIndexByName("Cluster id (cl)")
        cloud.setCurrentScalarField(cl_index)
        cloud.setCurrentDisplayedScalarField(cl_index)
        cloud.showSF(True)
        report(100, _tr("progress.cluster_analysis_complete"))
        return diagnostics, results, "Success"
    except CalculationCancelledException:
        return None, None, _tr("cancel.user")


# ---------------------------------------------------------
# Normal spacing and persistence analyses
# ---------------------------------------------------------
def _cluster_plane_groups(cloud, family_id, d_tolerance=1.0e-5):
    """Group positive clusters of one JS family by coincident D values."""
    required = ("Discontinuity Set (DS)", "Cluster id (cl)", "A", "B", "C", "D")
    indices = {name: cloud.getScalarFieldIndexByName(name) for name in required}
    missing = [name for name, index in indices.items() if index < 0]
    if missing:
        raise ValueError(_tr("error.missing_scalar_fields", fields=", ".join(missing)))
    coordinates = np.asarray(cloud.points(), dtype=np.float64)
    fields = {
        name: np.asarray(cloud.getScalarField(index).asArray()).copy()
        for name, index in indices.items()
    }
    mask = (fields["Discontinuity Set (DS)"].astype(int) == int(family_id)) & (fields["Cluster id (cl)"] > 0)
    family_global = np.flatnonzero(mask)
    if family_global.size == 0:
        return []
    groups = []
    for cluster_id in sorted(np.unique(fields["Cluster id (cl)"][family_global].astype(int))):
        cluster_global = family_global[fields["Cluster id (cl)"][family_global].astype(int) == cluster_id]
        D = float(np.median(fields["D"][cluster_global]))
        normal = np.array([
            np.median(fields["A"][cluster_global]),
            np.median(fields["B"][cluster_global]),
            np.median(fields["C"][cluster_global]),
        ], dtype=np.float64)
        length = np.linalg.norm(normal)
        if length <= np.finfo(float).eps:
            continue
        normal /= length
        target = None
        for group in groups:
            if np.isclose(D, group["D"], rtol=0.0, atol=float(d_tolerance)):
                target = group
                break
        if target is None:
            groups.append({
                "family_id": int(family_id), "D": D, "normal": normal,
                "cluster_ids": [int(cluster_id)],
                "global_indices": cluster_global.copy(),
            })
        else:
            target["cluster_ids"].append(int(cluster_id))
            target["global_indices"] = np.concatenate([
                target["global_indices"], cluster_global
            ])
    for plane_id, group in enumerate(sorted(groups, key=lambda item: item["D"]), start=1):
        group["plane_id"] = plane_id
        group["points"] = coordinates[group["global_indices"]]
    return sorted(groups, key=lambda item: item["D"])


def _positive_reflection_kde(values, bandwidth=0.0, grid_count=512):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values) & (values > 0.0)]
    if values.size == 0:
        return np.array([]), np.array([]), np.nan
    if values.size == 1 or np.allclose(values, values[0]):
        width = float(bandwidth) if bandwidth > 0 else max(values[0] * 0.1, 1.0e-6)
        x = np.linspace(0.0, max(values[0] * 2.0, width * 5.0), grid_count)
        density_values = np.exp(-0.5 * ((x - values[0]) / width) ** 2)
        density_values += np.exp(-0.5 * ((x + values[0]) / width) ** 2)
        density_values /= max(np.trapz(density_values, x), np.finfo(float).eps)
        return density_values, x, width
    reflected = np.concatenate([values, -values])
    kde = gaussian_kde(reflected)
    if bandwidth > 0:
        sample_std = np.std(reflected, ddof=1)
        factor = float(bandwidth) / sample_std if sample_std > 0 else 1.0
        kde.set_bandwidth(bw_method=factor)
        width = float(bandwidth)
    else:
        width = float(kde.factor * np.std(reflected, ddof=1))
    x = np.linspace(0.0, max(values.max() * 1.25, width * 5.0), grid_count)
    return 2.0 * kde(x), x, width


def analyze_normal_spacing(
        cloud, family_id, bandwidth=0.0, minimum_spacing=0.01,
        d_tolerance=1.0e-5, progress_callback=None):
    def report(percent, text):
        if progress_callback and progress_callback(percent, text) is False:
            raise CalculationCancelledException(_tr("cancel.user"))

    report(0, _tr("progress.reading_positive_clusters"))
    groups = _cluster_plane_groups(cloud, family_id, d_tolerance)
    # _cluster_plane_groups applies Cluster id (cl) > 0, so discard 0 is never used.
    if len(groups) <= 1:
        raise ValueError(_tr("error.two_planes_required"))

    groups = sorted(groups, key=lambda item: item["D"])
    group_count = len(groups)
    point_blocks = [group["points"] for group in groups]
    point_counts = np.asarray([len(points) for points in point_blocks], dtype=int)
    all_points = np.concatenate(point_blocks, axis=0)
    all_plane_ids = np.concatenate([
        np.full(count, index + 1, dtype=np.int32)
        for index, count in enumerate(point_counts)
    ])

    nonpersistent = []
    full_persistent = []
    iteration_count = group_count - 1
    for position, group in enumerate(groups[:-1]):
        report(
            5.0 + 80.0 * position / max(iteration_count, 1),
            _tr("progress.spacing_plane", position=position + 1, total=iteration_count)
        )
        current_plane_id = position + 1
        other_mask = all_plane_ids != current_plane_id
        other_points = all_points[other_mask]
        other_plane_ids = all_plane_ids[other_mask]

        # This is equivalent to the original MATLAB knnsearch call. Building the
        # tree on the smaller side reduces memory and query overhead.
        current_points = group["points"]
        if len(current_points) <= len(other_points):
            tree = cKDTree(current_points)
            distances, _ = tree.query(other_points, k=1, workers=-1)
            nearest_other_row = int(np.argmin(distances))
            nearest_plane_id = int(other_plane_ids[nearest_other_row])
        else:
            tree = cKDTree(other_points)
            distances, nearest_rows = tree.query(
                current_points, k=1, workers=-1
            )
            nearest_current_row = int(np.argmin(distances))
            nearest_plane_id = int(
                other_plane_ids[int(nearest_rows[nearest_current_row])]
            )

        nearest = groups[nearest_plane_id - 1]
        nonpersistent.append([
            int(family_id), group["plane_id"], nearest["plane_id"],
            abs(group["D"] - nearest["D"]), group["D"], nearest["D"]
        ])
        following = groups[position + 1]
        full_persistent.append([
            int(family_id), group["plane_id"], following["plane_id"],
            abs(group["D"] - following["D"]), group["D"], following["D"]
        ])

    report(87, _tr("progress.filtering_spacing"))
    raw_nfp = np.asarray(nonpersistent, dtype=float)
    raw_fp = np.asarray(full_persistent, dtype=float)
    filtered = raw_nfp[raw_nfp[:, 3] > float(minimum_spacing)]
    if filtered.size:
        _, unique_indices = np.unique(filtered[:, 3], return_index=True)
        filtered = filtered[np.sort(unique_indices)]
    filtered_fp = raw_fp[raw_fp[:, 3] > float(minimum_spacing)]
    kde_nfp, x_nfp, bw_nfp = _positive_reflection_kde(
        filtered[:, 3] if filtered.size else [], bandwidth)
    kde_fp, x_fp, bw_fp = _positive_reflection_kde(
        filtered_fp[:, 3] if filtered_fp.size else [], 0.0)
    values = filtered[:, 3] if filtered.size else np.array([])
    values_fp = filtered_fp[:, 3] if filtered_fp.size else np.array([])
    if values.size == 0:
        raise ValueError(_tr("error.no_spacing_values"))
    unique_values, counts = np.unique(np.sort(values), return_counts=True)
    mode_value = float(unique_values[np.argmax(counts)])
    report(100, _tr("progress.spacing_complete"))
    return {
        "family_id": int(family_id), "groups": groups,
        "nonpersistent_raw": raw_nfp, "full_persistent_raw": raw_fp,
        "nonpersistent": filtered, "full_persistent": filtered_fp,
        "kde_nonpersistent": kde_nfp, "x_nonpersistent": x_nfp,
        "kde_full": kde_fp, "x_full": x_fp,
        "bandwidth_nonpersistent": bw_nfp, "bandwidth_full": bw_fp,
        "mean": float(np.mean(values)), "min": float(np.min(values)),
        "max": float(np.max(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "mode": mode_value,
        "max_density_spacing": float(x_nfp[np.argmax(kde_nfp)]),
        "mean_full": float(np.mean(values_fp)) if values_fp.size else np.nan,
    }


def analyze_persistence(
        cloud, d_tolerance=1.0e-5, progress_callback=None):
    def report(percent, text):
        if progress_callback and progress_callback(percent, text) is False:
            raise CalculationCancelledException(_tr("cancel.user"))

    report(0, _tr("progress.reading_ds_families"))
    ds_index = cloud.getScalarFieldIndexByName("Discontinuity Set (DS)")
    if ds_index < 0:
        raise ValueError(_tr("error.ds_field_missing"))
    ds_values = np.asarray(cloud.getScalarField(ds_index).asArray(), dtype=int)
    family_ids = sorted(value for value in np.unique(ds_values) if value > 0)
    family_groups = [
        (int(family_id), _cluster_plane_groups(
            cloud, int(family_id), d_tolerance
        ))
        for family_id in family_ids
    ]
    total_groups = sum(len(groups) for _, groups in family_groups)
    if total_groups == 0:
        return [], []

    rows = []
    summaries = []
    completed = 0
    for family_position, (family_id, groups) in enumerate(family_groups, start=1):
        for group_position, group in enumerate(groups, start=1):
            report(
                5.0 + 90.0 * completed / total_groups,
                _tr("progress.persistence_plane", family=family_id, family_position=family_position, family_total=len(family_groups), plane=group_position, plane_total=len(groups))
            )
            completed += 1
            points = group["points"]
            if len(points) < 3:
                continue
            normal = group["normal"] / np.linalg.norm(group["normal"])
            reference = np.array([0.0, 0.0, 1.0])
            if abs(np.dot(normal, reference)) > 0.9:
                reference = np.array([1.0, 0.0, 0.0])
            strike_axis = np.cross(reference, normal)
            strike_axis /= np.linalg.norm(strike_axis)
            dip_axis = np.cross(normal, strike_axis)
            dip_axis /= np.linalg.norm(dip_axis)
            centered = points - points.mean(axis=0)
            projected = np.column_stack((
                centered @ dip_axis, centered @ strike_axis
            ))
            p_dip = float(np.ptp(projected[:, 0]))
            p_strike = float(np.ptp(projected[:, 1]))
            try:
                hull = ConvexHull(projected)
                hull_points = projected[hull.vertices]
                area = float(hull.volume)
                p_max = (
                    float(np.max(distance.pdist(hull_points)))
                    if len(hull_points) > 1 else 0.0
                )
            except QhullError:
                area = 0.0
                p_max = (
                    float(np.max(distance.pdist(projected)))
                    if len(projected) > 1 else 0.0
                )
            rows.append({
                "family_id": family_id,
                "plane_id": group["plane_id"],
                "cluster_ids": tuple(group["cluster_ids"]),
                "D": group["D"], "n_points": len(points),
                "p_dip": p_dip, "p_strike": p_strike,
                "p_max": p_max, "area": area,
            })
        family_rows = [
            row for row in rows if row["family_id"] == family_id
        ]
        if family_rows:
            summaries.append({
                "family_id": family_id,
                "n_planes": len(family_rows),
                "mean_pmax": float(np.mean([
                    row["p_max"] for row in family_rows
                ])),
                "max_pmax": float(np.max([
                    row["p_max"] for row in family_rows
                ])),
                "mean_pdip": float(np.mean([
                    row["p_dip"] for row in family_rows
                ])),
                "mean_pstrike": float(np.mean([
                    row["p_strike"] for row in family_rows
                ])),
                "mean_area": float(np.mean([
                    row["area"] for row in family_rows
                ])),
            })
    report(100, _tr("progress.persistence_complete"))
    return rows, summaries


def _positive_cluster_groups(cloud, family_ids=None):
    """Return each positive DBSCAN cluster independently, without D merging."""
    required = (
        "Discontinuity Set (DS)", "Raw cluster id (cl_raw)",
        "A_raw", "B_raw", "C_raw", "D_raw"
    )
    indices = {
        name: cloud.getScalarFieldIndexByName(name) for name in required
    }
    missing = [name for name, index in indices.items() if index < 0]
    if missing:
        raise ValueError(_tr("error.missing_scalar_fields", fields=", ".join(missing)))

    coordinates = np.asarray(cloud.points(), dtype=np.float64)
    fields = {
        name: np.asarray(cloud.getScalarField(index).asArray()).copy()
        for name, index in indices.items()
    }
    ds_values = fields["Discontinuity Set (DS)"].astype(np.int32)
    cluster_values = fields["Raw cluster id (cl_raw)"].astype(np.int32)
    available = sorted(int(value) for value in np.unique(ds_values) if value > 0)
    selected = available if family_ids is None else [int(value) for value in family_ids]

    groups = []
    for family_id in selected:
        family_mask = (ds_values == family_id) & (cluster_values > 0)
        for cluster_id in sorted(np.unique(cluster_values[family_mask])):
            global_indices = np.flatnonzero(
                family_mask & (cluster_values == int(cluster_id))
            )
            if global_indices.size < 3:
                continue
            normal = np.array([
                np.median(fields["A_raw"][global_indices]),
                np.median(fields["B_raw"][global_indices]),
                np.median(fields["C_raw"][global_indices]),
            ], dtype=np.float64)
            normal_length = np.linalg.norm(normal)
            if normal_length <= np.finfo(float).eps:
                continue
            normal /= normal_length
            groups.append({
                "family_id": int(family_id),
                "cluster_id": int(cluster_id),
                "cluster_ids": (int(cluster_id),),
                "plane_id": int(cluster_id),
                "D": float(np.median(fields["D_raw"][global_indices])),
                "normal": normal,
                "global_indices": global_indices,
                "points": coordinates[global_indices],
            })
    return groups


def _local_plane_coordinates(points, normal):
    normal = np.asarray(normal, dtype=np.float64)
    normal /= np.linalg.norm(normal)
    vertical = np.array([0.0, 0.0, 1.0])
    strike = np.cross(vertical, normal)
    if np.linalg.norm(strike) < 1.0e-10:
        strike = np.array([1.0, 0.0, 0.0])
    strike /= np.linalg.norm(strike)
    dip = np.cross(normal, strike)
    dip /= np.linalg.norm(dip)
    centered = np.asarray(points, dtype=np.float64) - np.mean(points, axis=0)
    return np.column_stack((centered @ dip, centered @ strike, centered @ normal))


def _profile_z2(local_points, center_strike, band_width, sample_interval,
                minimum_samples=10):
    selected = local_points[
        np.abs(local_points[:, 1] - float(center_strike)) <= float(band_width) / 2.0
    ]
    if len(selected) < minimum_samples:
        return None
    order = np.argsort(selected[:, 0])
    u = selected[order, 0]
    z = selected[order, 2]
    umin, umax = float(u.min()), float(u.max())
    if umax - umin < sample_interval * (minimum_samples - 1):
        return None
    edges = np.arange(umin, umax + sample_interval, sample_interval)
    if len(edges) < minimum_samples + 1:
        return None
    bins = np.digitize(u, edges) - 1
    centers, heights = [], []
    for index in range(len(edges) - 1):
        values = z[bins == index]
        if values.size:
            centers.append((edges[index] + edges[index + 1]) / 2.0)
            heights.append(float(np.median(values)))
    if len(centers) < minimum_samples:
        return None
    x = np.asarray(centers)
    y = np.asarray(heights)
    # Remove the best-fit linear trend before measuring microscopic roughness.
    y = y - np.polyval(np.polyfit(x, y, 1), x)
    dx = np.diff(x)
    valid = dx > 0
    if np.count_nonzero(valid) < minimum_samples - 1:
        return None
    slopes = np.diff(y)[valid] / dx[valid]
    z2 = float(np.sqrt(np.mean(slopes * slopes)))
    if not np.isfinite(z2) or z2 <= 0:
        return None
    # Tse and Cruden relation, calibrated for 0.5 mm sampling interval.
    jrc_raw = float(32.2 + 32.47 * np.log10(z2))
    jrc = float(np.clip(jrc_raw, 0.0, 20.0))
    clipping = "low" if jrc_raw < 0.0 else ("high" if jrc_raw > 20.0 else "none")
    return {"z2": z2, "jrc_raw": jrc_raw, "jrc": jrc,
            "jrc_clipping": clipping, "samples": len(x),
            "length": float(x[-1] - x[0]), "center_strike": float(center_strike)}


def analyze_roughness(
        cloud, family_ids=None, profiles_per_plane=10,
        band_width=0.0, sample_interval=0.0005,
        minimum_samples=10, d_tolerance=1.0e-5,
        progress_callback=None):
    del d_tolerance

    def report(percent, text):
        if progress_callback and progress_callback(percent, text) is False:
            raise CalculationCancelledException(_tr("cancel.user"))

    interval = float(sample_interval)
    if not np.isfinite(interval) or interval <= 0.0:
        raise ValueError(_tr("error.sampling_positive"))
    profile_count = max(int(profiles_per_plane), 1)
    minimum_count = max(int(minimum_samples), 3)

    report(0, _tr("progress.reading_independent_clusters"))
    groups = _positive_cluster_groups(cloud, family_ids=family_ids)
    if not groups:
        return [], [], []

    profiles = []
    cluster_rows = []
    family_rows = []
    total_profiles = len(groups) * profile_count
    processed_profiles = 0

    for cluster_position, group in enumerate(groups, start=1):
        report(
            5.0 + 90.0 * processed_profiles / max(total_profiles, 1),
            f"DS {group['family_id']}, cluster {group['cluster_id']} "
            f"({cluster_position}/{len(groups)}): preparing local plane..."
        )
        local = _local_plane_coordinates(group["points"], group["normal"])
        strike_min = float(np.min(local[:, 1]))
        strike_max = float(np.max(local[:, 1]))
        strike_range = strike_max - strike_min
        if strike_range <= 0.0:
            processed_profiles += profile_count
            continue

        width = float(band_width)
        if width <= 0.0:
            width = max(strike_range / profile_count, interval * 2.0)
        if width >= strike_range:
            centers = np.array([(strike_min + strike_max) / 2.0])
        else:
            centers = np.linspace(
                strike_min + width / 2.0,
                strike_max - width / 2.0,
                profile_count
            )

        cluster_profiles = []
        for profile_id, center in enumerate(centers, start=1):
            report(
                5.0 + 90.0 * processed_profiles / max(total_profiles, 1),
                _tr("progress.roughness_profile", family=group['family_id'], cluster=group['cluster_id'], profile=profile_id, total=len(centers))
            )
            processed_profiles += 1
            result = _profile_z2(
                local, center, width, interval, minimum_count
            )
            if result is None:
                continue
            row = {
                "family_id": group["family_id"],
                "plane_id": group["cluster_id"],
                "cluster_id": group["cluster_id"],
                "cluster_ids": (group["cluster_id"],),
                "profile_id": profile_id,
                "D": group["D"], "band_width": width,
                "sample_interval": interval, **result
            }
            profiles.append(row)
            cluster_profiles.append(row)

        if cluster_profiles:
            jrc_values = np.asarray([
                row["jrc"] for row in cluster_profiles
            ], dtype=np.float64)
            z2_values = np.asarray([
                row["z2"] for row in cluster_profiles
            ], dtype=np.float64)
            cluster_rows.append({
                "family_id": group["family_id"],
                "plane_id": group["cluster_id"],
                "cluster_id": group["cluster_id"],
                "cluster_ids": (group["cluster_id"],),
                "D": group["D"],
                "profiles": len(cluster_profiles),
                "mean_z2": float(z2_values.mean()),
                "mean_jrc": float(jrc_values.mean()),
                "std_jrc": (
                    float(jrc_values.std(ddof=1))
                    if len(jrc_values) > 1 else 0.0
                ),
                "min_jrc": float(jrc_values.min()),
                "max_jrc": float(jrc_values.max()),
            })

    selected_families = sorted({
        group["family_id"] for group in groups
    })
    for family_id in selected_families:
        family_profiles = [
            row for row in profiles if row["family_id"] == family_id
        ]
        if not family_profiles:
            continue
        values = np.asarray([
            row["jrc"] for row in family_profiles
        ], dtype=np.float64)
        family_rows.append({
            "family_id": family_id,
            "profiles": len(values),
            "clusters": len({
                row["cluster_id"] for row in family_profiles
            }),
            "planes": len({
                row["cluster_id"] for row in family_profiles
            }),
            "mean": float(values.mean()),
            "median": float(np.median(values)),
            "std": (
                float(values.std(ddof=1)) if len(values) > 1 else 0.0
            ),
            "min": float(values.min()),
            "max": float(values.max()),
            "q25": float(np.percentile(values, 25)),
            "q75": float(np.percentile(values, 75)),
        })

    report(100, _tr("stereo.roughness_complete"))
    return profiles, cluster_rows, family_rows

