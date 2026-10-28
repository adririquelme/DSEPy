# -*- coding: utf-8 -*-
"""
DSE technical report generator.

Builds a client-ready technical report (self-contained HTML and/or Markdown
with a figures folder) from the results recorded by the DSE workflow.

This module is independent from CloudCompare and Tkinter: it only consumes a
plain ``data`` dictionary (see ``generate_report``) so it can be tested
without the GUI.  Figures are rendered off-screen with the Agg backend and
equations are rendered as images with matplotlib mathtext, so the output does
not need MathJax or an Internet connection.

``data`` keys (every section is optional and omitted when ``None``):
    cloud        {"name", "points"}
    colour       optimisation parameters/result + "normals_sample"
    step1        projection, bins, min_angle, max_poles, density_style,
                 space, n_poles, poles{space: (x, y)}, grids{space: (X, Y, Z)}
    poles        list of principal-pole dicts (live table, after manual edits)
    poles_status "automatic" | "validated" | "empty"
    step2        cone, counts{family: n}, total, plot (x, y, family),
                 projection
    step3        method, params, stats, results, fisher
    spacing      params, results
    persistence  params, rows, summaries
``info`` keys: project, client, author, date, report_version, software_version,
location, observations, language ("en" | "es").
"""

import base64
import datetime
import html
import io
import os
import re
import struct
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import colour_optimisation as colour_opt
import stereonet

MAX_PLOT_POINTS = 150000
MAX_TABLE_ROWS = 1000
FORMATS = ("html", "markdown")
LANGUAGES = ("en", "es")

OBJECTIVE_LATEX = {
    "potential_linear": r"f(\beta)=\beta",
    "potential_quadratic": r"f(\beta)=\beta^{2}",
    "potential_cubic": r"f(\beta)=\beta^{3}",
    "rational_vertical_asymptote":
        r"f(\beta)=\frac{1}{91^{\circ}-\beta}-\frac{1}{91^{\circ}}",
    "steps": r"f(\beta)=\frac{1}{1000}\,[\,1000\ (\beta\geq75^{\circ}),\ "
             r"10\ (60^{\circ}<\beta<75^{\circ}),\ 0\ (\beta\leq60^{\circ})\,]",
}
PROJECTION_LATEX = {
    "Equal-angle": r"r=\tan\left(\frac{\beta}{2}\right)",
    "Equal-area": r"r=\sqrt{2}\,\sin\left(\frac{\beta}{2}\right)",
    "Equal-proportion": r"r=\frac{2\beta}{\pi}",
}


def subsample_points(*arrays, limit=MAX_PLOT_POINTS, seed=0):
    """Return the same random subset of every array (for lightweight storage)."""
    arrays = [np.asarray(a) for a in arrays]
    count = len(arrays[0])
    if count <= limit:
        return tuple(a.copy() for a in arrays)
    index = np.sort(np.random.default_rng(seed).choice(count, limit, replace=False))
    return tuple(a[index] for a in arrays)


# ---------------------------------------------------------------------------
# Document model (rendered to HTML or Markdown)
# ---------------------------------------------------------------------------
class _Document:
    def __init__(self, language):
        self.language = language
        self.blocks = []
        self.assets = {}
        self.figures = 0
        self.tables = 0
        self.equations = 0

    def L(self, en, es):
        return es if self.language == "es" else en

    def heading(self, level, text):
        self.blocks.append(("h", level, text))

    def paragraph(self, text):
        self.blocks.append(("p", text))

    def bullets(self, items):
        self.blocks.append(("ul", list(items)))

    def note(self, text):
        self.blocks.append(("note", text))

    def pagebreak(self):
        self.blocks.append(("pb",))

    def table(self, headers, rows, caption):
        self.tables += 1
        label = "{} {}. {}".format(self.L("Table", "Tabla"), self.tables, caption)
        self.blocks.append(("table", list(headers), [list(map(str, r)) for r in rows], label))

    def key_values(self, pairs, caption):
        self.table([self.L("Parameter", "Parámetro"), self.L("Value", "Valor")],
                   [(k, v) for k, v in pairs], caption)

    def equation(self, mathtext):
        self.equations += 1
        name = "equation_{:02d}.png".format(self.equations)
        self.assets[name] = _render_equation(mathtext)
        self.blocks.append(("eq", name, self.equations))

    def figure(self, fig, caption, width=100):
        self.figures += 1
        name = "figure_{:02d}.png".format(self.figures)
        self.assets[name] = _figure_png(fig)
        label = "{} {}. {}".format(self.L("Figure", "Figura"), self.figures, caption)
        self.blocks.append(("fig", name, label, width))


_PAGE_WIDTH_IN = 6.5   # A4 with 2 cm margins leaves 17 cm (6.7 in) of text width
_PAGE_HEIGHT_IN = 8.0  # leaves room for the caption on the same page
_FIGURE_DPI = 170
_EQUATION_DPI = 200


def _png_size(png):
    return struct.unpack(">II", png[16:24])


def _figure_png(fig, dpi=_FIGURE_DPI):
    # Shrink oversized figures to the A4 text width while keeping the font
    # sizes, so labels stay readable at the printed size.
    width, height = fig.get_size_inches()
    # Never shrink below 70 %: the browser/print scaling does the rest and
    # keeps multi-panel stereonets from becoming cramped.
    scale = max(0.7, min(1.0, _PAGE_WIDTH_IN / width, _PAGE_HEIGHT_IN / height))
    if scale < 1.0:
        fig.set_size_inches(width * scale, height * scale)
    FigureCanvasAgg(fig)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()


def _render_equation(mathtext):
    fig = Figure(figsize=(0.1, 0.1))
    fig.text(0.0, 0.0, "$" + mathtext + "$", fontsize=12)
    FigureCanvasAgg(fig)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=_EQUATION_DPI, bbox_inches="tight",
                pad_inches=0.04, transparent=True)
    return buffer.getvalue()


def _css_width(png, dpi):
    """Width in CSS pixels (96 per inch) that reproduces the physical size."""
    return int(round(_png_size(png)[0] * 96.0 / dpi))


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _fmt(value, digits=2):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if np.isnan(value):
        return "-"
    if np.isinf(value):
        return "inf"
    return "{:.{}f}".format(value, digits)


def _gfmt(value, digits=4):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if np.isnan(value):
        return "-"
    return "{:.{}g}".format(value, digits)


def _family_label(family_id):
    return "J_{}".format(int(family_id))


def _stereonet_axes(fig, rect, projection, labeled=1):
    ax = fig.add_axes(rect)
    stereonet.draw_stereonet(ax, projection=projection, labeled=labeled)
    return ax


def _pole_xy(pole, projection, rotation=None):
    """Projected position of a principal pole in the original or rotated space."""
    if rotation is None:
        dipdir, dip = pole["dipdir"], pole["dip"]
    else:
        rotated = np.asarray(rotation, float) @ np.asarray(pole["normal"], float)
        dipdir, dip = stereonet.f_vnorm2clar_v02(rotated.reshape(1, 3))
        dipdir, dip = dipdir[0], dip[0]
    x, y = stereonet.f_clar2cart(dipdir, dip, projection=projection)
    return float(np.atleast_1d(x)[0]), float(np.atleast_1d(y)[0])


def _mark_poles(ax, poles, projection, rotation=None):
    for pole in poles:
        x, y = _pole_xy(pole, projection, rotation)
        ax.plot(x, y, "o", markersize=6, markerfacecolor="yellow",
                markeredgecolor="black", markeredgewidth=1.0, zorder=10)
        ax.text(x + 0.035, y + 0.025, "$J_{{{}}}$".format(pole.get("idx", 1)),
                fontsize=10, fontweight="bold", zorder=11)


def _space_title(doc, space):
    return doc.L("Rotated space", "Espacio rotado") if space == "rotated" \
        else doc.L("Original space", "Espacio original")


def _rotation(data):
    colour = data.get("colour")
    if colour and colour.get("rotation") is not None:
        return np.asarray(colour["rotation"], dtype=float)
    return None


def _pairwise_angles(poles):
    normals = np.asarray([p["normal"] for p in poles], dtype=float)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    return np.degrees(np.arccos(np.clip(np.abs(normals @ normals.T), 0.0, 1.0)))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _section_cover(doc, info, data):
    L = doc.L
    cloud = data.get("cloud") or {}
    doc.key_values([
        (L("Project", "Proyecto"), info.get("project") or "-"),
        (L("Client", "Cliente"), info.get("client") or "-"),
        (L("Site / location", "Emplazamiento"), info.get("location") or "-"),
        (L("Author", "Autor"), info.get("author") or "-"),
        (L("Date", "Fecha"), info.get("date") or "-"),
        (L("Report version", "Versión del informe"), info.get("report_version") or "-"),
        (L("Software", "Software"), "DSE - Discontinuity Set Extractor {}".format(
            info.get("software_version", ""))),
        (L("Point cloud", "Nube de puntos"), cloud.get("name") or "-"),
        (L("Number of points", "Número de puntos"),
         "{:,}".format(int(cloud["points"])) if cloud.get("points") else "-"),
    ], L("Report identification", "Identificación del informe"))
    if info.get("observations"):
        doc.heading(2, L("Observations", "Observaciones"))
        for chunk in re.split(r"\n\s*\n", info["observations"].strip()):
            doc.paragraph(chunk.strip())


def _section_summary(doc, data, included):
    L = doc.L
    doc.heading(1, L("1. Scope and summary", "1. Alcance y resumen"))
    doc.paragraph(L(
        "This report documents the calculations carried out with DSE "
        "(Discontinuity Set Extractor) on the point cloud identified above: the "
        "parameters used, the methods applied and the results obtained, so that "
        "the analysis can be reviewed and reproduced.",
        "Este informe documenta los cálculos realizados con DSE (Discontinuity "
        "Set Extractor) sobre la nube de puntos indicada: parámetros empleados, "
        "métodos aplicados y resultados obtenidos, de modo que el análisis pueda "
        "revisarse y reproducirse."))
    doc.bullets(included)
    poles = data.get("poles") or []
    if poles:
        rows = [(_family_label(p["idx"]), "{:05.1f}".format(p["dipdir"]),
                 "{:04.1f}".format(p["dip"])) for p in poles]
        doc.table([L("Family", "Familia"), L("Dip direction (°)", "Dirección de buzamiento (°)"),
                   L("Dip (°)", "Buzamiento (°)")], rows,
                  L("Summary of the discontinuity sets (principal poles)",
                    "Resumen de las familias de discontinuidades (polos principales)"))


def _section_colour(doc, data, number):
    colour = data.get("colour")
    if not colour:
        return
    L = doc.L
    params = colour.get("params", {})
    objective = colour.get("objective_name") or params.get("objective", "")
    angles = np.asarray(colour["angles"], dtype=float)
    rotation = np.asarray(colour["rotation"], dtype=float)
    manual = bool(colour.get("manual"))
    doc.heading(1, "{}. {}".format(number, L("Orientation colour optimisation",
                                             "Optimización del color por orientación")))
    doc.paragraph(L(
        "The reference system used to colour the normals is rotated so that the "
        "poles are kept away from the border of the stereonet (steep dips), "
        "where colour changes are abrupt. The rotation R is searched by "
        "minimising the mean of a penalty function f of the dip β of the "
        "rotated poles, using differential evolution.",
        "El sistema de referencia empleado para colorear las normales se rota "
        "para alejar los polos del borde del estereograma (buzamientos "
        "elevados), donde los cambios de color son bruscos. La rotación R se "
        "obtiene minimizando la media de una función de penalización f del "
        "buzamiento β de los polos rotados, mediante evolución diferencial."))
    doc.equation(r"J(\theta)=\frac{1}{N}\sum_{i=1}^{N} f\left(\beta_i(\theta)\right),"
                 r"\qquad \mathbf{n}_i'=R(\theta)\,\mathbf{n}_i,\qquad "
                 r"\beta_i=\arccos\left|n'_{i,z}\right|")
    if objective in OBJECTIVE_LATEX:
        doc.paragraph(L("Penalty function selected ({}):", "Función de penalización seleccionada ({}):")
                      .format(objective))
        doc.equation(OBJECTIVE_LATEX[objective])
    dof = angles.size
    if dof == 3:
        doc.paragraph(L(
            "Three degrees of freedom: intrinsic ZYX Euler rotation (angles in degrees).",
            "Tres grados de libertad: rotación de Euler intrínseca ZYX (ángulos en grados)."))
        doc.equation(r"R=R_z(\psi)\,R_y(\theta)\,R_x(\phi)")
        names = ["ψ (Z)", "θ (Y)", "φ (X)"]
    else:
        doc.paragraph(L(
            "Two degrees of freedom: rotation defined by azimuth α and tilt β "
            "(angles in degrees).",
            "Dos grados de libertad: rotación definida por acimut α e inclinación β "
            "(ángulos en grados)."))
        names = ["α", "β"]
    rows = [
        (L("Degrees of freedom", "Grados de libertad"), dof),
        (L("Objective function", "Función objetivo"), objective),
        (L("Method", "Método"), L("Manual angles entered by the user", "Ángulos introducidos manualmente")
         if manual else L("Differential evolution (best1bin, polished)",
                          "Evolución diferencial (best1bin, con pulido final)")),
    ]
    if not manual:
        rows += [
            (L("Working sample (% of normals)", "Muestra de trabajo (% de normales)"),
             params.get("subsample", "-")),
            (L("Maximum iterations", "Iteraciones máximas"), params.get("iterations", "-")),
            (L("Population size", "Tamaño de población"), params.get("population", "-")),
            (L("Random seed", "Semilla aleatoria"), params.get("seed") or L("random", "aleatoria")),
        ]
    rows += [
        (L("Colour space", "Espacio de color"), params.get("space", "-")),
        (L("Lightness", "Luminosidad"), params.get("lightness", "-")),
    ]
    doc.key_values(rows, L("Colour optimisation parameters", "Parámetros de la optimización del color"))

    result_rows = [(n, _fmt(a, 4) + " °") for n, a in zip(names, angles)]
    result_rows.append((L("Objective value J", "Valor de la función objetivo J"),
                        _gfmt(colour.get("objective"), 8)))
    equivalent = colour.get("equivalent_degrees")
    if equivalent is not None and np.isfinite(equivalent):
        result_rows.append((L("Equivalent dip (°)", "Buzamiento equivalente (°)"), _fmt(equivalent, 2)))
    if not manual:
        result_rows += [
            (L("Function evaluations", "Evaluaciones de la función"), colour.get("evaluations", "-")),
            (L("Iterations", "Iteraciones"), colour.get("iterations", "-")),
            (L("Computation time (s)", "Tiempo de cálculo (s)"), _fmt(colour.get("seconds"), 2)),
            (L("Converged", "Convergencia"), L("yes", "sí") if colour.get("success") else L("no", "no")),
        ]
    doc.key_values(result_rows, L("Optimisation result", "Resultado de la optimización"))

    doc.paragraph(L("Resulting rotation matrix R (applied as n' = R·n):",
                    "Matriz de rotación R resultante (se aplica como n' = R·n):"))
    doc.table(["", "x", "y", "z"],
              [[r] + ["{:+.6f}".format(v) for v in rotation[i]] for i, r in enumerate(("x'", "y'", "z'"))],
              L("Rotation matrix", "Matriz de rotación"))

    normals = colour.get("normals_sample")
    if normals is not None and len(normals):
        projection = colour.get("projection", "Equal-angle")
        normals = np.asarray(normals, float)
        rotated_x, rotated_y, rotated_n, valid = colour_opt.projected_poles_from_normals(
            normals, angles, projection=projection)
        rgb = colour_opt.colours_from_projected_poles(
            rotated_x, rotated_y, params.get("space", "HSV"),
            float(params.get("lightness", 80)), valid=valid)
        dipdir, dip = stereonet.f_vnorm2clar_v02(normals)
        ox, oy = stereonet.f_clar2cart(dipdir, dip, projection=projection)
        fig = Figure(figsize=(11, 5.6))
        for position, (x, y, title) in enumerate((
                (ox[valid], oy[valid], L("Original poles", "Polos originales")),
                (rotated_x[valid], rotated_y[valid], L("Rotated poles", "Polos rotados")))):
            ax = _stereonet_axes(fig, (0.02 + 0.5 * position, 0.02, 0.46, 0.88), projection, 0)
            ax.scatter(x, y, s=3, c=rgb[valid].astype(float) / 255.0, edgecolors="none",
                       alpha=0.85, zorder=0)
            ax.set_title(title, fontsize=11)
        doc.figure(fig, L("Poles coloured with the optimised orientation colour map "
                          "(same colours in both spaces; {} projection, {:,} sampled normals).",
                          "Polos coloreados con el mapa de color por orientación optimizado "
                          "(mismos colores en ambos espacios; proyección {}, {:,} normales muestreadas).")
                   .format(projection, len(normals)))

        original_dip = colour_opt.dips_from_normals(normals)
        rotated_dip = colour_opt.dips_from_normals(rotated_n)
        fig = Figure(figsize=(7.5, 3.6))
        ax = fig.add_subplot(111)
        bins = np.linspace(0, 90, 37)
        ax.hist(original_dip, bins=bins, alpha=0.6, label=L("Original", "Original"), color="#4c78a8")
        ax.hist(rotated_dip, bins=bins, alpha=0.6, label=L("Rotated", "Rotado"), color="#f58518")
        ax.set_xlabel(L("Dip β of the poles (°)", "Buzamiento β de los polos (°)"))
        ax.set_ylabel(L("Number of normals", "Número de normales"))
        ax.legend()
        ax.grid(alpha=0.2)
        fig.tight_layout()
        doc.figure(fig, L("Dip distribution of the normals before and after the rotation.",
                          "Distribución del buzamiento de las normales antes y después de la rotación."))


def _section_step1(doc, data, number):
    step1 = data.get("step1")
    poles = data.get("poles") or []
    if not step1:
        return
    L = doc.L
    projection = step1["projection"]
    rotation = _rotation(data)
    detection_space = step1.get("space", "original")
    doc.heading(1, "{}. {}".format(number, L("Principal poles (Step 1)", "Polos principales (Paso 1)")))

    doc.heading(2, number_label(number, 1) + L("Method", "Método"))
    doc.paragraph(L(
        "Poles (unit normals flipped to the lower hemisphere) are projected on the "
        "stereonet with the {} projection. The distance r to the centre depends on the "
        "dip β of the pole:".format(projection),
        "Los polos (normales unitarias llevadas al hemisferio inferior) se proyectan en el "
        "estereograma con la proyección {}. La distancia r al centro depende del "
        "buzamiento β del polo:".format(projection)))
    doc.equation(PROJECTION_LATEX.get(projection, PROJECTION_LATEX["Equal-angle"]))
    doc.paragraph(L(
        "The pole density is estimated with the adaptive diffusion kernel density "
        "estimator of Botev et al. (2010) on a regular grid of {0}×{0} cells (2^{1}). "
        "Density is normalised to 0-100 %. Principal poles are the local maxima of the "
        "density surface (density > 0.5 %), sorted by decreasing density; a maximum is "
        "accepted only if its angle with every already accepted pole is at least {2}° "
        "(axial angle), up to a maximum of {3} poles.".format(
            step1["grid_res"], step1["bins"], _gfmt(step1["min_angle"]), step1["max_poles"]),
        "La densidad de polos se estima con el estimador de densidad por núcleo de difusión "
        "adaptativo de Botev et al. (2010) sobre una malla regular de {0}×{0} celdas (2^{1}). "
        "La densidad se normaliza a 0-100 %. Los polos principales son los máximos locales de "
        "la superficie de densidad (densidad > 0.5 %), ordenados por densidad decreciente; un "
        "máximo se acepta solo si su ángulo con cada polo ya aceptado es al menos {2}° "
        "(ángulo axial), hasta un máximo de {3} polos.".format(
            step1["grid_res"], step1["bins"], _gfmt(step1["min_angle"]), step1["max_poles"])))
    if detection_space == "rotated":
        doc.paragraph(L(
            "The density maxima were searched in the rotated space (see the colour "
            "optimisation section) and converted back to the original reference system "
            "with n = Rᵀ·n', so all orientations reported below refer to the real "
            "(original) coordinate system.",
            "Los máximos de densidad se buscaron en el espacio rotado (véase la sección de "
            "optimización del color) y se convirtieron al sistema de referencia original "
            "con n = Rᵀ·n', por lo que todas las orientaciones indicadas se refieren al "
            "sistema de coordenadas real (original)."))
    status = data.get("poles_status")
    if status == "validated":
        doc.note(L("The table of principal poles was reviewed/edited manually by the "
                   "user (validated).",
                   "La tabla de polos principales fue revisada/editada manualmente por el "
                   "usuario (validada)."))
    doc.key_values([
        (L("Projection", "Proyección"), projection),
        (L("Number of poles (points)", "Número de polos (puntos)"), "{:,}".format(int(step1["n_poles"]))),
        (L("Density grid", "Malla de densidad"), "{0}×{0} (2^{1})".format(step1["grid_res"], step1["bins"])),
        (L("Minimum angle between poles (°)", "Ángulo mínimo entre polos (°)"), _gfmt(step1["min_angle"])),
        (L("Maximum number of poles", "Número máximo de polos"), step1["max_poles"]),
        (L("Space of the density search", "Espacio de búsqueda de la densidad"),
         _space_title(doc, detection_space)),
    ], L("Step 1 parameters", "Parámetros del Paso 1"))

    doc.heading(2, number_label(number, 2) + L("Stereonet of poles", "Estereograma de polos"))
    spaces = [s for s in ("original", "rotated") if s in step1.get("poles", {})]
    fig = Figure(figsize=(5.8 * len(spaces), 5.8))
    for position, space in enumerate(spaces):
        x, y = step1["poles"][space]
        ax = _stereonet_axes(fig, (position / len(spaces) + 0.01, 0.02, 0.98 / len(spaces) - 0.02, 0.88),
                             projection, 0 if space == "rotated" else 1)
        ax.plot(x, y, "b.", markersize=1.0, alpha=0.4, zorder=0)
        ax.set_title("{} ({:,} {})".format(_space_title(doc, space), int(step1["n_poles"]),
                                           L("poles", "polos")), fontsize=11)
    doc.figure(fig, L("Stereonet of poles ({} projection, lower hemisphere).",
                      "Estereograma de polos (proyección {}, hemisferio inferior).").format(projection))

    doc.heading(2, number_label(number, 3) + L("Pole density stereonet", "Estereograma de densidad de polos"))
    grids = step1.get("grids", {})
    spaces = [s for s in ("original", "rotated") if s in grids]
    fig = Figure(figsize=(6.4 * len(spaces), 5.8))
    filled = step1.get("density_style") == "Filled Contours"
    for position, space in enumerate(spaces):
        ax = fig.add_axes((position / len(spaces) + 0.01, 0.04, 0.88 / len(spaces), 0.86))
        X, Y, Z = grids[space]
        contour = stereonet.draw_density_from_grid(
            ax, X, Y, Z, projection=projection, labeled=0 if space == "rotated" else 1,
            filled=filled, n_levels=40, principal_poles=None)
        if space == "rotated" and rotation is not None:
            _mark_poles(ax, poles, projection, rotation)
        elif space == "original":
            _mark_poles(ax, poles, projection)
        ax.set_title(_space_title(doc, space), fontsize=11)
        if contour is not None:
            contour.set_clim(0.0, 100.0)
            colorbar = fig.colorbar(contour, ax=ax, shrink=0.75, ticks=[0, 25, 50, 75, 100])
            colorbar.set_label(L("Relative density (%)", "Densidad relativa (%)"))
    doc.figure(fig, L("Pole density stereonet with the principal poles (yellow markers).",
                      "Estereograma de densidad de polos con los polos principales (marcadores amarillos)."))

    doc.heading(2, number_label(number, 4) + L("Principal poles", "Polos principales"))
    rows = []
    rotated = []
    for pole in poles:
        normal = np.asarray(pole["normal"], float)
        rows.append((_family_label(pole["idx"]), "{:.1f}".format(pole["dipdir"]),
                     "{:.1f}".format(pole["dip"]), _fmt(pole.get("density", 0.0), 1),
                     "{:+.4f}".format(normal[0]), "{:+.4f}".format(normal[1]), "{:+.4f}".format(normal[2])))
        if rotation is not None:
            nr = rotation @ normal
            if nr[2] < 0:
                nr = -nr
            dd, dp = stereonet.f_vnorm2clar_v02(nr.reshape(1, 3))
            rotated.append((_family_label(pole["idx"]), "{:.1f}".format(dd[0]), "{:.1f}".format(dp[0])))
    doc.table([L("Family", "Familia"), L("Dip direction (°)", "Dir. buzamiento (°)"), L("Dip (°)", "Buzamiento (°)"),
               L("Density (%)", "Densidad (%)"), "n_x", "n_y", "n_z"], rows,
              L("Principal poles in the original reference system (unit normal n = (n_x, n_y, n_z))",
                "Polos principales en el sistema de referencia original (normal unitaria n = (n_x, n_y, n_z))"))
    if rotated:
        doc.table([L("Family", "Familia"), L("Dip direction (°)", "Dir. buzamiento (°)"),
                   L("Dip (°)", "Buzamiento (°)")], rotated,
                  L("Principal poles in the rotated reference system", "Polos principales en el sistema de referencia rotado"))

    if len(poles) > 1:
        doc.heading(2, number_label(number, 5) + L("Angles between principal poles",
                                                   "Ángulos entre polos principales"))
        doc.paragraph(L("The angle between two sets is the axial angle between their poles:",
                        "El ángulo entre dos familias es el ángulo axial entre sus polos:"))
        doc.equation(r"\theta_{ij}=\arccos\left|\,\mathbf{n}_i\cdot\mathbf{n}_j\,\right|")
        angles = _pairwise_angles(poles)
        labels = [_family_label(p["idx"]) for p in poles]
        doc.table([""] + labels,
                  [[labels[i]] + [_fmt(v, 1) for v in angles[i]] for i in range(len(poles))],
                  L("Angles between principal poles (°)", "Ángulos entre polos principales (°)"))


def number_label(number, sub):
    return "{}.{} ".format(number, sub)


def _section_step2(doc, data, number):
    step2 = data.get("step2")
    poles = data.get("poles") or []
    if not step2:
        return
    L = doc.L
    doc.heading(1, "{}. {}".format(number, L("Assignment to discontinuity sets (Step 2)",
                                             "Asignación a familias de discontinuidades (Paso 2)")))
    doc.paragraph(L(
        "Each point is assigned to the principal pole with the smallest axial angle "
        "between its normal and the pole. If that angle is greater than the cone "
        "threshold θc the point is left unclassified (DS = 0).",
        "Cada punto se asigna al polo principal con menor ángulo axial entre su normal y el "
        "polo. Si dicho ángulo supera el umbral del cono θc, el punto queda sin clasificar "
        "(DS = 0)."))
    doc.equation(r"\theta_{ik}=\arccos\left|\,\mathbf{n}_i\cdot\mathbf{p}_k\,\right|,\qquad "
                 r"k^{*}=\arg\min_k\,\theta_{ik}")
    doc.equation(r"DS_i=k^{*}\ \ \mathrm{if}\ \ \theta_{ik^{*}}\leq\theta_c,\qquad DS_i=0\ \ \mathrm{otherwise}")
    doc.key_values([(L("Cone threshold θc (°)", "Umbral del cono θc (°)"), _gfmt(step2["cone"])),
                    (L("Number of points", "Número de puntos"), "{:,}".format(int(step2["total"])))],
                   L("Step 2 parameters", "Parámetros del Paso 2"))
    total = max(int(step2["total"]), 1)
    fisher = {p["idx"]: p for p in poles}
    rows = []
    for family_id in sorted(step2["counts"]):
        count = int(step2["counts"][family_id])
        if family_id == 0:
            rows.append((L("Unclassified", "Sin clasificar"), "{:,}".format(count),
                         _fmt(100.0 * count / total, 2), "-", "-"))
            continue
        pole = fisher.get(family_id, {})
        rows.append((_family_label(family_id), "{:,}".format(count), _fmt(100.0 * count / total, 2),
                     _fmt(pole.get("fisher_k"), 2) if "fisher_k" in pole else "-",
                     _fmt(pole.get("fisher_r"), 2) if "fisher_r" in pole else "-"))
    doc.table([L("Set", "Familia"), L("Points", "Puntos"), "%", "Fisher K", "R"], rows,
              L("Points assigned to each discontinuity set", "Puntos asignados a cada familia"))
    doc.paragraph(L("The Fisher concentration parameter of each set is computed with the axial "
                    "normals of its points (N points, resultant length R):",
                    "El parámetro de concentración de Fisher de cada familia se calcula con las "
                    "normales axiales de sus puntos (N puntos, longitud resultante R):"))
    doc.equation(r"K=\frac{N-1}{N-R}")

    plot = step2.get("plot")
    if plot is not None:
        projection = step2["projection"]
        xp, yp, family = plot
        family = np.asarray(family).astype(int)
        fig = Figure(figsize=(6.6, 6.0))
        ax = _stereonet_axes(fig, (0.01, 0.02, 0.98, 0.9), projection, 1)
        cmap = _tab10()
        for family_id in sorted(np.unique(family).tolist()):
            mask = family == family_id
            color = "0.6" if family_id == 0 else cmap((family_id - 1) % 10)
            label = L("Unclassified", "Sin clasificar") if family_id == 0 else _family_label(family_id)
            ax.plot(xp[mask], yp[mask], ".", color=color, markersize=1.4, alpha=0.5,
                    label="{} ({:,})".format(label, int(step2["counts"].get(family_id, mask.sum()))))
        _mark_poles(ax, poles, projection)
        legend = ax.legend(loc="upper right", markerscale=6, fontsize=8)
        legend.set_zorder(20)
        doc.figure(fig, L("Stereonet of the assignment of poles to discontinuity sets (cone threshold {}°).",
                          "Estereograma de asignación de polos a familias (umbral del cono {}°).")
                   .format(_gfmt(step2["cone"])))


def _tab10():
    from matplotlib import colormaps
    return colormaps["tab10"]


def _section_step3(doc, data, number):
    step3 = data.get("step3")
    if not step3:
        return
    L = doc.L
    params = step3["params"]
    method = step3["method"]
    doc.heading(1, "{}. {}".format(number, L("Spatial clustering and plane fitting (Step 3)",
                                             "Clusterización espacial y ajuste de planos (Paso 3)")))
    doc.heading(2, number_label(number, 1) + L("Method", "Método"))
    if method == "DBSCAN":
        doc.paragraph(L(
            "The points of each discontinuity set are clustered in 3D with DBSCAN. The "
            "neighbourhood radius ε is estimated automatically for every set from the "
            "distance to the k-th nearest neighbour: ε = μ + kσ·s, where μ and s are the mean "
            "and standard deviation of those distances.",
            "Los puntos de cada familia se agrupan en 3D con DBSCAN. El radio de vecindad ε "
            "se estima automáticamente para cada familia a partir de la distancia al k-ésimo "
            "vecino más próximo: ε = μ + kσ·s, siendo μ y s la media y la desviación típica "
            "de dichas distancias."))
        doc.equation(r"\varepsilon=\mu_k+k_\sigma\,s_k")
    else:
        doc.paragraph(L(
            "The points of each discontinuity set are clustered in 3D with HDBSCAN "
            "(hierarchical density-based clustering), which does not require a "
            "neighbourhood radius.",
            "Los puntos de cada familia se agrupan en 3D con HDBSCAN (clusterización jerárquica "
            "basada en densidad), que no requiere un radio de vecindad."))
    doc.paragraph(L(
        "Clusters smaller than the minimum size are discarded. A plane Ax + By + Cz + D = 0 "
        "(unit normal) is fitted to every cluster and its roughness is measured by the standard "
        "deviation σ of the orthogonal residuals:",
        "Los clusters menores que el tamaño mínimo se descartan. A cada cluster se le ajusta un "
        "plano Ax + By + Cz + D = 0 (normal unitaria) y se mide su rugosidad mediante la "
        "desviación típica σ de los residuos ortogonales:"))
    doc.equation(r"r_i=A x_i+B y_i+C z_i+D,\qquad \sigma=\sqrt{\frac{\sum_i r_i^{2}}{N-1}}")
    fixed = params.get("fix_orientation")
    if fixed:
        doc.paragraph(L(
            "The orientation of every plane is fixed to that of the principal pole of its set; "
            "only the offset D is fitted (D = −n·c, with c the centroid of the cluster).",
            "La orientación de cada plano se fija a la del polo principal de su familia; solo se "
            "ajusta el término D (D = −n·c, siendo c el centroide del cluster)."))
        merge = float(params.get("merge_sigma", 0.0))
        if merge > 0.0:
            doc.paragraph(L(
                "Clusters of the same set that are coplanar are merged: two clusters are "
                "connected when the distance between their planes does not exceed {0} times the "
                "sum of their σ, and the connected components are merged into a single plane.",
                "Los clusters coplanares de una misma familia se fusionan: dos clusters se "
                "conectan cuando la distancia entre sus planos no supera {0} veces la suma de sus "
                "σ, y las componentes conexas se fusionan en un único plano.").format(_gfmt(merge)))
            doc.equation(r"\left|D_i-D_j\right|\leq k_m\,(\sigma_i+\sigma_j)")
    else:
        doc.paragraph(L("The orientation of every plane is the free best fit (SVD) of its cluster; "
                        "no coplanarity merge is applied.",
                        "La orientación de cada plano es el mejor ajuste libre (SVD) de su cluster; "
                        "no se aplica fusión de planos coplanares."))
    sort_names = {"size": L("decreasing size", "tamaño decreciente"), "D": L("offset D", "término D"),
                  "random": L("random", "aleatorio")}
    rows = [(L("Method", "Método"), method)]
    if method == "DBSCAN":
        rows += [("k (" + L("neighbours", "vecinos") + ")", params.get("k_neighbor")),
                 ("kσ", _gfmt(params.get("k_sigma"))),
                 ("minPts", params.get("dbscan_minpts"))]
    else:
        rows += [("min_samples", params.get("hdbscan_min_samples")),
                 (L("Cluster selection", "Selección de clusters"), params.get("hdbscan_selection"))]
    rows += [(L("Minimum cluster size (points)", "Tamaño mínimo de cluster (puntos)"),
              params.get("minimum_cluster_size")),
             (L("Fix orientation to the principal pole", "Fijar orientación al polo principal"),
              L("yes", "sí") if fixed else L("no", "no")),
             (L("Coplanarity merge factor km", "Factor de fusión coplanar km"), _gfmt(params.get("merge_sigma"))),
             (L("Cluster numbering", "Numeración de clusters"), sort_names.get(params.get("sort_by"), params.get("sort_by"))),
             (L("Random seed", "Semilla aleatoria"), params.get("random_seed") if params.get("random_seed") is not None else "-")]
    doc.key_values(rows, L("Clustering parameters", "Parámetros de la clusterización"))

    doc.heading(2, number_label(number, 2) + L("Clustering summary", "Resumen de la clusterización"))
    stats_rows = []
    for family_id in sorted(step3["stats"]):
        info = step3["stats"][family_id]
        row = [_family_label(family_id), "{:,}".format(int(info.get("pts", 0)))]
        if method == "DBSCAN":
            row.append(_gfmt(info.get("eps"), 4))
        row += [info.get("clusters_before_merge", "-"), info.get("clusters_after_merge", "-"),
                "{:,}".format(int(info.get("raw_noise", 0))), "{:,}".format(int(info.get("rejected_points", 0))),
                "{:,}".format(int(info.get("zero_points", 0)))]
        stats_rows.append(row)
    headers = [L("Set", "Familia"), L("Points", "Puntos")]
    if method == "DBSCAN":
        headers.append("ε")
    headers += [L("Clusters before merge", "Clusters antes de fusión"), L("Clusters after merge", "Clusters tras fusión"),
                L("Noise", "Ruido"), L("Rejected (size)", "Rechazados (tamaño)"), L("Unclustered", "Sin cluster")]
    doc.table(headers, stats_rows, L("Clustering statistics per discontinuity set",
                                     "Estadísticas de clusterización por familia"))

    doc.heading(2, number_label(number, 3) + L("Fitted planes", "Planos ajustados"))
    plane_rows = []
    for family_id in sorted(step3["results"]):
        for cluster_id, info in sorted(step3["results"][family_id].items()):
            a, b, c = info["normal"]
            plane_rows.append((_family_label(family_id), cluster_id, "{:.1f}".format(info["dipdir"]),
                               "{:.1f}".format(info["dip"]), "{:+.4f}".format(a), "{:+.4f}".format(b),
                               "{:+.4f}".format(c), _gfmt(info["D"], 6), _gfmt(info.get("sigma"), 4),
                               "{:,}".format(int(info["n_pts"]))))
    shown = plane_rows[:MAX_TABLE_ROWS]
    doc.table([L("Set", "Familia"), "cl", L("Dip dir. (°)", "Dir. buz. (°)"), L("Dip (°)", "Buz. (°)"),
               "A", "B", "C", "D", "σ", L("Points", "Puntos")], shown,
              L("Fitted planes (Ax + By + Cz + D = 0)", "Planos ajustados (Ax + By + Cz + D = 0)"))
    if len(plane_rows) > len(shown):
        doc.note(L("Only the first {} of {} planes are listed.", "Solo se listan los primeros {} de {} planos.")
                 .format(len(shown), len(plane_rows)))

    projection = (data.get("step1") or {}).get("projection") or "Equal-angle"
    fig = Figure(figsize=(6.4, 6.0))
    ax = _stereonet_axes(fig, (0.01, 0.02, 0.98, 0.9), projection, 1)
    cmap = _tab10()
    for family_id in sorted(step3["results"]):
        planes = step3["results"][family_id]
        if not planes:
            continue
        x, y = stereonet.f_clar2cart([p["dipdir"] for p in planes.values()],
                                     [p["dip"] for p in planes.values()], projection=projection)
        sizes = np.array([p["n_pts"] for p in planes.values()], dtype=float)
        ax.scatter(x, y, s=12 + 60 * sizes / max(sizes.max(), 1.0), color=cmap((family_id - 1) % 10),
                   edgecolors="black", linewidths=0.4, alpha=0.85, label=_family_label(family_id), zorder=5)
    ax.legend(loc="upper right", fontsize=8)
    doc.figure(fig, L("Poles of the fitted cluster planes (marker size proportional to the number of points).",
                      "Polos de los planos de cluster ajustados (tamaño proporcional al número de puntos)."))

    fisher = step3.get("fisher") or []
    if fisher:
        doc.heading(2, number_label(number, 4) + L("Orientation dispersion of the planes",
                                                   "Dispersión de orientación de los planos"))
        doc.paragraph(L(
            "Fisher statistics of the fitted cluster planes of each set (N planes). Confidence "
            "cones of 63 % and 95 % are computed as 81/√(K·N) and 140/√(K·N) (degrees).",
            "Estadísticos de Fisher de los planos de cluster de cada familia (N planos). Los conos "
            "de confianza del 63 % y 95 % se calculan como 81/√(K·N) y 140/√(K·N) (grados)."))
        rows = []
        for item in fisher:
            k_value, n_value = float(item["K"]), int(item["N"])
            cone = lambda factor: ("{:.1f}".format(factor / np.sqrt(k_value * n_value))
                                   if n_value >= 3 and k_value > 0 else "-")
            rows.append((_family_label(item["family_id"]), "{:.1f}".format(item["dipdir"]),
                         "{:.1f}".format(item["dip"]), n_value, _fmt(k_value, 2),
                         _fmt(item["max_deviation"], 1), cone(81.0), cone(140.0)))
        doc.table([L("Set", "Familia"), L("Dip dir. (°)", "Dir. buz. (°)"), L("Dip (°)", "Buz. (°)"), "N", "K",
                   L("Max. deviation (°)", "Desv. máx. (°)"), "63 % (°)", "95 % (°)"], rows,
                  L("Fisher statistics of the cluster planes", "Estadísticos de Fisher de los planos de cluster"))


def _grid_figure(count, width=5.2, height=3.9):
    columns = 1 if count == 1 else 2 if count <= 4 else 3
    rows = int(np.ceil(count / columns))
    fig = Figure(figsize=(width * columns, height * rows), layout="constrained")
    axes = [fig.add_subplot(rows, columns, i + 1) for i in range(count)]
    return fig, axes


def _section_spacing(doc, data, number):
    spacing = data.get("spacing")
    if not spacing or not spacing.get("results"):
        return
    L = doc.L
    params = spacing["params"]
    results = spacing["results"]
    doc.heading(1, "{}. {}".format(number, L("Normal spacing analysis", "Análisis de espaciado normal")))
    doc.paragraph(L(
        "Cluster planes of each set are ordered by their offset D. For every plane the "
        "spacing is the normal distance to (a) its nearest plane of the set (non-persistent "
        "spacing) and (b) the next plane in the ordering (full-persistent spacing). Spacings "
        "below the minimum are discarded and the distribution is estimated with a Gaussian kernel "
        "density estimator reflected at zero.",
        "Los planos de cluster de cada familia se ordenan por su término D. Para cada plano, el "
        "espaciado es la distancia normal a (a) su plano más cercano de la familia (espaciado "
        "no persistente) y (b) el siguiente plano en la ordenación (espaciado de persistencia "
        "total). Los espaciados inferiores al mínimo se descartan y la distribución se estima con "
        "un estimador de densidad de núcleo gaussiano reflejado en cero."))
    doc.equation(r"s_{ij}=\left|D_i-D_j\right|")
    doc.key_values([
        (L("Bandwidth (0 = automatic)", "Ancho de banda (0 = automático)"), _gfmt(params.get("bandwidth"))),
        (L("Minimum spacing", "Espaciado mínimo"), _gfmt(params.get("minimum"))),
        (L("D tolerance (plane grouping)", "Tolerancia de D (agrupación de planos)"), _gfmt(params.get("tolerance"))),
    ], L("Spacing parameters", "Parámetros del espaciado"))
    rows = [(_family_label(r["family_id"]), len(r["groups"]), _gfmt(r["mean"]), _gfmt(r["std"]), _gfmt(r["min"]),
             _gfmt(r["max"]), _gfmt(r["mode"]), _gfmt(r["max_density_spacing"]), _gfmt(r["mean_full"]))
            for r in results]
    doc.table([L("Set", "Familia"), L("Planes", "Planos"), L("Mean S1", "Media S1"), L("Std. dev.", "Desv. típ."),
               L("Min", "Mín"), L("Max", "Máx"), L("Mode", "Moda"), L("Max. density", "Máx. densidad"),
               L("Mean S2", "Media S2")], rows,
              L("Normal spacing per set (S1: non-persistent, S2: full persistent)",
                "Espaciado normal por familia (S1: no persistente, S2: persistencia total)"))
    fig, axes = _grid_figure(len(results))
    for axis, result in zip(axes, results):
        axis.plot(result["x_nonpersistent"], result["kde_nonpersistent"], "b--", linewidth=1.4,
                  label=L("Non-persistent", "No persistente"))
        axis.plot(result["x_full"], result["kde_full"], "g-", linewidth=1.4,
                  label=L("Full persistent", "Persistencia total"))
        axis.set_title("{}\nS1={}; S2={}".format(_family_label(result["family_id"]), _gfmt(result["mean"]),
                                                 _gfmt(result["mean_full"])), fontsize=9)
        axis.set_xlabel(L("Spacing", "Espaciado"))
        axis.set_ylabel(L("Density", "Densidad"))
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    doc.figure(fig, L("Spacing distribution (kernel density) per discontinuity set.",
                      "Distribución del espaciado (densidad de núcleo) por familia."))


def _section_persistence(doc, data, number):
    persistence = data.get("persistence")
    if not persistence or not persistence.get("rows"):
        return
    L = doc.L
    rows = persistence["rows"]
    doc.heading(1, "{}. {}".format(number, L("Persistence analysis", "Análisis de persistencia")))
    doc.paragraph(L(
        "Each fitted plane is projected on its own plane and the trace lengths along the dip "
        "(P_dip) and strike (P_strike) directions, the maximum persistence (P_max, largest "
        "distance between projected points) and the area of the plane are computed.",
        "Cada plano ajustado se proyecta sobre sí mismo y se calculan las longitudes de traza "
        "según el buzamiento (P_dip) y el rumbo (P_strike), la persistencia máxima (P_max, "
        "mayor distancia entre puntos proyectados) y el área del plano."))
    doc.key_values([(L("D tolerance (plane grouping)", "Tolerancia de D (agrupación de planos)"),
                     _gfmt(persistence["params"].get("tolerance")))],
                   L("Persistence parameters", "Parámetros de persistencia"))
    summaries = persistence.get("summaries") or []
    if summaries:
        doc.table([L("Set", "Familia"), L("Planes", "Planos"), L("Mean P_max", "P_max medio"),
                   L("Max. P_max", "P_max máximo"), L("Mean P_dip", "P_dip medio"),
                   L("Mean P_strike", "P_strike medio"), L("Mean area", "Área media")],
                  [(_family_label(s["family_id"]), s["n_planes"], _gfmt(s["mean_pmax"]), _gfmt(s["max_pmax"]),
                    _gfmt(s["mean_pdip"]), _gfmt(s["mean_pstrike"]), _gfmt(s["mean_area"]))
                   for s in summaries],
                  L("Persistence summary per set", "Resumen de persistencia por familia"))
    ids = sorted({row["family_id"] for row in rows})
    fig, axes = _grid_figure(len(ids), height=3.5)
    for axis, family_id in zip(axes, ids):
        values = [r["p_max"] for r in rows if r["family_id"] == family_id]
        axis.hist(values, bins="auto", color="#4c78a8", edgecolor="white", linewidth=0.8)
        axis.set_title("{} (N={}, {}={})".format(_family_label(family_id), len(values), L("mean", "media"),
                                                  _gfmt(np.mean(values), 3)), fontsize=9)
        axis.set_xlabel("P_max")
        axis.set_ylabel(L("Planes", "Planos"))
        axis.grid(alpha=0.2)
    doc.figure(fig, L("Histogram of the maximum persistence per set.",
                      "Histograma de la persistencia máxima por familia."))
    shown = rows[:MAX_TABLE_ROWS]
    doc.table([L("Set", "Familia"), L("Plane", "Plano"), "D", L("Points", "Puntos"), "P_dip", "P_strike", "P_max",
               L("Area", "Área")],
              [(_family_label(r["family_id"]), r["plane_id"], _gfmt(r["D"], 6), "{:,}".format(int(r["n_points"])),
                _gfmt(r["p_dip"]), _gfmt(r["p_strike"]), _gfmt(r["p_max"]), _gfmt(r["area"])) for r in shown],
              L("Persistence of every plane", "Persistencia de cada plano"))
    if len(rows) > len(shown):
        doc.note(L("Only the first {} of {} planes are listed.", "Solo se listan los primeros {} de {} planos.")
                 .format(len(shown), len(rows)))


def _section_references(doc, number):
    L = doc.L
    doc.heading(1, "{}. {}".format(number, L("References", "Referencias")))
    doc.bullets([
        "Riquelme, A.J., Abellán, A., Tomás, R., Jaboyedoff, M. (2014). A new approach for semi-automatic "
        "rock mass joints recognition from 3D point clouds. Computers & Geosciences. "
        "https://doi.org/10.1016/j.cageo.2014.03.014",
        "Riquelme, A.J., Tomás, R., Abellán, A. (2016). Characterization of rock slopes through slope mass "
        "rating using 3D point clouds. Int. J. Rock Mech. Min. Sci. https://doi.org/10.1016/j.ijrmms.2015.12.008",
        "Riquelme, A.J., Abellán, A., Tomás, R. (2015). Discontinuity spacing analysis in rock masses using 3D "
        "point clouds. Engineering Geology. https://doi.org/10.1016/j.enggeo.2015.06.009",
        "Orientation-based colour mapping: https://doi.org/10.1016/j.jrmge.2025.12.059",
        "Botev, Z.I., Grotowski, J.F., Kroese, D.P. (2010). Kernel density estimation via diffusion. "
        "Annals of Statistics, 38(5), 2916-2957.",
    ])


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
_CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;color:#1f2933;max-width:17cm;margin:2em auto;padding:0 1em;line-height:1.5;font-size:11pt}
h1{border-bottom:2px solid #2b5c8a;color:#1d3f5f;padding-bottom:.2em;margin-top:2em;font-size:1.6em}
h2{color:#2b5c8a;margin-top:1.4em;font-size:1.25em} h1.title{font-size:2em;border:none;margin-bottom:0}
table{border-collapse:collapse;margin:.4em 0 1.2em;width:100%;font-size:.85em}
th,td{border:1px solid #c5ced8;padding:3px 7px;text-align:center} th{background:#e8eff6}
td:first-child{text-align:left}
caption{caption-side:top;text-align:left;font-weight:600;padding:.4em 0}
figure{margin:1em 0;text-align:center} figure img{max-width:100%;height:auto}
figcaption{font-size:.85em;color:#52606d}
.eq{text-align:center;margin:.5em 0}.eq img{vertical-align:middle;max-width:100%;height:auto}
.eq .n{float:right;color:#52606d}
.note{background:#fff8e1;border-left:4px solid #f0b429;padding:.4em .8em;margin:.8em 0}
.pagebreak{page-break-after:always}
@page{size:A4;margin:20mm}
@media print{body{max-width:none;margin:0;padding:0}h1{page-break-before:always}h1.title{page-break-before:avoid}
figure,table{page-break-inside:avoid}}
"""


def _data_uri(png):
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def render_html(doc, title, subtitle):
    e = html.escape
    out = ["<!DOCTYPE html><html lang=\"{}\"><head><meta charset=\"utf-8\"><title>{}</title>"
           "<style>{}</style></head><body>".format(doc.language, e(title), _CSS),
           "<h1 class=\"title\">{}</h1><p>{}</p>".format(e(title), e(subtitle))]
    for block in doc.blocks:
        kind = block[0]
        if kind == "h":
            out.append("<h{0}>{1}</h{0}>".format(block[1], e(block[2])))
        elif kind == "p":
            out.append("<p>{}</p>".format(e(block[1])))
        elif kind == "ul":
            out.append("<ul>{}</ul>".format("".join("<li>{}</li>".format(e(i)) for i in block[1])))
        elif kind == "note":
            out.append("<div class=\"note\">{}</div>".format(e(block[1])))
        elif kind == "pb":
            out.append("<div class=\"pagebreak\"></div>")
        elif kind == "eq":
            out.append("<div class=\"eq\"><img src=\"{}\" alt=\"equation\" style=\"width:{}px\"></div>".format(
                _data_uri(doc.assets[block[1]]), _css_width(doc.assets[block[1]], _EQUATION_DPI)))
        elif kind == "fig":
            out.append("<figure><img src=\"{}\" alt=\"{}\" style=\"width:{}px\"><figcaption>{}</figcaption></figure>"
                       .format(_data_uri(doc.assets[block[1]]), e(block[2]),
                               _css_width(doc.assets[block[1]], _FIGURE_DPI), e(block[2])))
        elif kind == "table":
            head = "".join("<th>{}</th>".format(e(str(h))) for h in block[1])
            body = "".join("<tr>{}</tr>".format("".join("<td>{}</td>".format(e(c)) for c in row))
                           for row in block[2])
            out.append("<table><caption>{}</caption><thead><tr>{}</tr></thead><tbody>{}</tbody></table>"
                       .format(e(block[3]), head, body))
    out.append("</body></html>")
    return "\n".join(out)


def render_markdown(doc, title, subtitle, assets_folder):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    out = ["# " + title, "", subtitle, ""]
    for block in doc.blocks:
        kind = block[0]
        if kind == "h":
            out += ["#" * (block[1] + 1) + " " + block[2], ""]
        elif kind == "p":
            out += [block[1], ""]
        elif kind == "ul":
            out += ["- " + item for item in block[1]] + [""]
        elif kind == "note":
            out += ["> " + block[1], ""]
        elif kind == "eq":
            out += ["![equation]({}/{})".format(assets_folder, block[1]), ""]
        elif kind == "fig":
            out += ["![{0}]({1}/{2})".format(cell(block[2]), assets_folder, block[1]), "", "*" + block[2] + "*", ""]
        elif kind == "table":
            out += ["**" + block[3] + "**", "",
                    "| " + " | ".join(cell(h) for h in block[1]) + " |",
                    "|" + "|".join(" --- " for _ in block[1]) + "|"]
            out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in block[2]] + [""]
    return "\n".join(out)


def _safe_name(text):
    cleaned = re.sub(r"[^\w\-]+", "_", text or "", flags=re.UNICODE).strip("_")
    return cleaned or "DSE"


def build_document(data, info):
    """Assemble the report document model from recorded results."""
    language = info.get("language", "en")
    doc = _Document(language if language in LANGUAGES else "en")
    L = doc.L
    included = []
    sections = []
    if data.get("colour"):
        included.append(L("Orientation colour optimisation", "Optimización del color por orientación"))
        sections.append(_section_colour)
    if data.get("step1"):
        included.append(L("Principal poles extraction (Step 1)", "Extracción de polos principales (Paso 1)"))
        sections.append(_section_step1)
    if data.get("step2"):
        included.append(L("Assignment to discontinuity sets (Step 2)", "Asignación a familias (Paso 2)"))
        sections.append(_section_step2)
    if data.get("step3"):
        included.append(L("Spatial clustering and plane fitting (Step 3)",
                          "Clusterización espacial y ajuste de planos (Paso 3)"))
        sections.append(_section_step3)
    if data.get("spacing") and data["spacing"].get("results"):
        included.append(L("Normal spacing analysis", "Análisis de espaciado normal"))
        sections.append(_section_spacing)
    if data.get("persistence") and data["persistence"].get("rows"):
        included.append(L("Persistence analysis", "Análisis de persistencia"))
        sections.append(_section_persistence)
    if not sections:
        raise ValueError(L("There are no results to report. Run at least one analysis first.",
                           "No hay resultados que incluir. Ejecute al menos un análisis."))
    _section_cover(doc, info, data)
    _section_summary(doc, data, included)
    number = 2
    for section in sections:
        section(doc, data, number)
        number += 1
    _section_references(doc, number)
    return doc


def generate_report(data, info, output_folder, formats=("html",), progress=None):
    """Write the report and return the list of generated file paths."""
    formats = [f for f in formats if f in FORMATS]
    if not formats:
        raise ValueError("No output format selected")
    os.makedirs(output_folder, exist_ok=True)
    info = dict(info)
    info.setdefault("date", datetime.date.today().isoformat())
    if progress:
        progress(10)
    doc = build_document(data, info)
    if progress:
        progress(70)
    title = doc.L("DSE Technical Report", "Memoria técnica DSE")
    subtitle = "{} - {}".format(info.get("project") or "", info.get("date")).strip(" -")
    base = "DSE_report_{}".format(_safe_name(info.get("project")))
    paths = []
    if "html" in formats:
        path = os.path.join(output_folder, base + ".html")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(render_html(doc, title, subtitle))
        paths.append(path)
    if "markdown" in formats:
        folder_name = base + "_files"
        os.makedirs(os.path.join(output_folder, folder_name), exist_ok=True)
        for name, png in doc.assets.items():
            with open(os.path.join(output_folder, folder_name, name), "wb") as stream:
                stream.write(png)
        path = os.path.join(output_folder, base + ".md")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(render_markdown(doc, title, subtitle, folder_name))
        paths.append(path)
    if progress:
        progress(100)
    return paths
