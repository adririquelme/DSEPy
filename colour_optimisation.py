# -*- coding: utf-8 -*-
"""Normal-colour axis optimisation for DSE.

Numerical code is independent from Tk and CloudCompare. Angles exposed by the
public API are always degrees. Normals use row-vector shape (N, 3).
"""
from dataclasses import dataclass
import time
import numpy as np


_TRANSLATOR = None

def set_translator(translator):
    """Install the application translation function used by visible errors."""
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
from scipy.optimize import differential_evolution

OBJECTIVES = (
    "potential_linear", "potential_quadratic", "potential_cubic",
    "rational_vertical_asymptote", "steps",
)

@dataclass
class OptimisationResult:
    angles: np.ndarray
    rotation: np.ndarray
    objective: float
    equivalent_degrees: float
    evaluations: int
    iterations: int
    seconds: float
    success: bool
    message: str


def rotation_matrix_2dof(angles_deg):
    alpha, beta = np.deg2rad(np.asarray(angles_deg, dtype=float))
    u = np.array([np.cos(alpha), -np.sin(alpha), 0.0])
    v = np.array([np.cos(beta)*np.sin(alpha), np.cos(beta)*np.cos(alpha), -np.sin(beta)])
    w = np.array([np.sin(beta)*np.sin(alpha), np.sin(beta)*np.cos(alpha), np.cos(beta)])
    return np.column_stack((u, v, w))


def rotation_matrix_euler(angles_deg):
    """MATLAB eul2rotm-compatible intrinsic ZYX rotation."""
    z, y, x = np.deg2rad(np.asarray(angles_deg, dtype=float))
    cz, sz, cy, sy, cx, sx = np.cos(z), np.sin(z), np.cos(y), np.sin(y), np.cos(x), np.sin(x)
    rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]], float)
    ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]], float)
    rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]], float)
    return rz @ ry @ rx


def rotation_matrix(angles_deg):
    angles = np.asarray(angles_deg, dtype=float).ravel()
    if angles.size == 2:
        return rotation_matrix_2dof(angles)
    if angles.size == 3:
        return rotation_matrix_euler(angles)
    raise ValueError(_tr("colour.error.rotation_angles"))


def validate_normals(normals):
    values = np.asarray(normals, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError(_tr("colour.error.normals_shape"))
    lengths = np.linalg.norm(values, axis=1)
    valid = np.isfinite(values).all(axis=1) & (lengths > np.finfo(float).eps)
    values = values[valid]
    values /= np.linalg.norm(values, axis=1)[:, None]
    return values, valid


def rotate_to_upper_hemisphere(normals, angles_deg):
    values, _ = validate_normals(normals)
    rotated = (rotation_matrix(angles_deg) @ values.T).T
    rotated[rotated[:, 2] < 0.0] *= -1.0
    return rotated


def dips_from_normals(normals):
    values, _ = validate_normals(normals)
    z = np.clip(np.abs(values[:, 2]), 0.0, 1.0)
    return np.rad2deg(np.arccos(z))


def objective_value(angles_deg, normals, objective="rational_vertical_asymptote", weights=None):
    if objective not in OBJECTIVES:
        raise ValueError(_tr("colour.error.unknown_objective", objective=objective))
    rotated = rotate_to_upper_hemisphere(normals, angles_deg)
    dip = dips_from_normals(rotated)
    if weights is None:
        weight = np.ones(dip.size, dtype=float)
    else:
        weight = np.asarray(weights, dtype=float).ravel()
        if weight.size != dip.size:
            raise ValueError(_tr("colour.error.weights_length"))
        weight = np.where(np.isfinite(weight) & (weight >= 0), weight, 0.0)
    total = float(weight.sum())
    if total <= 0:
        raise ValueError(_tr("colour.error.weight_positive"))
    if objective == "potential_linear": values = dip
    elif objective == "potential_quadratic": values = dip**2
    elif objective == "potential_cubic": values = dip**3
    elif objective == "rational_vertical_asymptote":
        # 91 keeps the function finite at the 90 degree stereonet boundary.
        values = 1.0/(91.0-dip) - 1.0/91.0
    else:
        # Corrected from the MATLAB prototype: thresholds and dip are degrees.
        values = np.where(dip >= 75.0, 1000.0, np.where(dip > 60.0, 10.0, 0.0)) / 1000.0
    return float(np.sum(values * weight) / total)


def equivalent_degrees(value, objective):
    if objective == "potential_quadratic": return float(max(value, 0.0)**0.5)
    if objective == "potential_cubic": return float(max(value, 0.0)**(1.0/3.0))
    if objective == "potential_linear": return float(value)
    return float("nan")


def make_working_sample(normals, fraction=1.0, weights=None, seed=None):
    values, valid = validate_normals(normals)
    use_weights = None if weights is None else np.asarray(weights, dtype=float).ravel()[valid]
    fraction = float(fraction)
    if not 0.0 < fraction <= 1.0:
        raise ValueError(_tr("colour.error.subsample"))
    count = max(3, min(len(values), int(round(len(values)*fraction))))
    if count < len(values):
        rng = np.random.default_rng(seed)
        indices = rng.choice(len(values), size=count, replace=False)
        values = values[indices]
        if use_weights is not None: use_weights = use_weights[indices]
    return values, use_weights


def optimise_rotation(normals, degrees_of_freedom=2, objective="rational_vertical_asymptote",
                      subsample=1.0, weights=None, seed=None, max_iterations=80,
                      population_size=12, tolerance=1e-4, progress_callback=None):
    working, working_weights = make_working_sample(normals, subsample, weights, seed)
    dof = int(degrees_of_freedom)
    bounds = [(-180.0,180.0),(-45.0,45.0)] if dof == 2 else [(-180.0,180.0)]*3
    if dof not in (2,3): raise ValueError(_tr("colour.error.dof"))
    started = time.perf_counter(); iterations = [0]
    def fun(x): return objective_value(x, working, objective, working_weights)
    def callback(x, convergence=0.0):
        iterations[0] += 1
        if progress_callback:
            return progress_callback(iterations[0], int(max_iterations), float(fun(x)), float(convergence)) is False
        return False
    result = differential_evolution(fun, bounds, strategy="best1bin", maxiter=int(max_iterations),
        popsize=int(population_size), tol=float(tolerance), seed=seed, callback=callback,
        polish=True, updating="immediate", workers=1)
    angles = np.asarray(result.x, dtype=float)
    return OptimisationResult(angles, rotation_matrix(angles), float(result.fun),
        equivalent_degrees(result.fun, objective), int(result.nfev), iterations[0],
        time.perf_counter()-started, bool(result.success), str(result.message))


def _hsv_to_rgb(h, s, v):
    h=np.mod(h,1.0); i=np.floor(h*6).astype(int); f=h*6-i
    p=v*(1-s); q=v*(1-f*s); t=v*(1-(1-f)*s); i%=6
    choices=((v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q))
    return np.column_stack([np.choose(i,[c[k] for c in choices]) for k in range(3)])


def _lab_to_linear_srgb(lab):
    lab=np.asarray(lab,float); L,a,b=lab.T
    fy=(L+16.0)/116.0; fx=fy+a/500.0; fz=fy-b/200.0; delta=6.0/29.0
    inv=lambda q: np.where(q>delta,q**3,3.0*delta**2*(q-4.0/29.0))
    xyz=np.column_stack((0.95047*inv(fx),inv(fy),1.08883*inv(fz)))
    M=np.array([[3.2404542,-1.5371385,-0.4985314],[-0.9692660,1.8760108,0.0415560],[0.0556434,-0.2040259,1.0572252]])
    return xyz@M.T

def _encode_srgb(linear):
    return np.where(linear<=0.0031308,12.92*linear,1.055*np.maximum(linear,0.0)**(1.0/2.4)-0.055)

def _cielch_to_rgb_gamut_mapped(L,C,h,iterations=12):
    L=np.asarray(L,float); C=np.asarray(C,float); h=np.asarray(h,float)
    low=np.zeros_like(C); high=np.maximum(C,0.0)
    def convert(c):
        return _lab_to_linear_srgb(np.column_stack((L,c*np.cos(h),c*np.sin(h))))
    original=convert(high); valid=np.all((original>=0)&(original<=1),axis=1); low[valid]=high[valid]
    active=~valid
    for _ in range(iterations):
        mid=(low+high)/2.0; trial=convert(mid); ok=np.all((trial>=0)&(trial<=1),axis=1)
        low[active&ok]=mid[active&ok]; high[active&~ok]=mid[active&~ok]
    return np.clip(_encode_srgb(convert(low)),0,1)

def projected_poles_from_normals(normals, angles_deg, projection="Equal-angle"):
    """Rotate normals and return projected pole coordinates without losing rows.

    The returned arrays preserve the original point order. Invalid normals are
    marked with NaN so RGB values always remain aligned with CloudCompare points.
    """
    original = np.asarray(normals, dtype=np.float64)
    if original.ndim != 2 or original.shape[1] != 3:
        raise ValueError(_tr("colour.error.normals_shape"))
    lengths = np.linalg.norm(original, axis=1)
    valid = np.isfinite(original).all(axis=1) & (lengths > np.finfo(float).eps)
    unit = np.zeros_like(original)
    unit[valid] = original[valid] / lengths[valid, None]
    rotated = np.full_like(original, np.nan)
    rotated[valid] = (rotation_matrix(angles_deg) @ unit[valid].T).T
    lower = valid & (rotated[:, 2] < 0.0)
    rotated[lower] *= -1.0

    dipdir_deg = np.full(len(original), np.nan)
    dip_deg = np.full(len(original), np.nan)
    dipdir_deg[valid] = np.degrees(np.mod(
        np.arctan2(rotated[valid, 0], rotated[valid, 1]), 2.0 * np.pi
    ))
    dip_deg[valid] = np.degrees(np.arccos(np.clip(rotated[valid, 2], 0.0, 1.0)))
    dip_rad = np.radians(dip_deg)
    projection_name = str(projection)
    if projection_name == "Equal-area":
        radius = np.sqrt(2.0) * np.sin(dip_rad / 2.0)
    elif projection_name == "Equal-proportion":
        radius = dip_rad / (np.pi / 2.0)
    else:
        radius = np.tan(dip_rad / 2.0)

    # Same azimuth convention used by stereonet.f_clar2cart/o2a.
    alpha = np.radians(90.0 - dipdir_deg)
    x = radius * np.cos(alpha)
    y = radius * np.sin(alpha)
    return x, y, rotated, valid


def _oklab_to_linear_srgb(oklab):
    """Convert Oklab values to unclipped linear sRGB."""
    oklab = np.asarray(oklab, dtype=np.float64)
    L, a, b = oklab.T
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, ss = l_ ** 3, m_ ** 3, s_ ** 3
    return np.column_stack((
        4.0767416621*l - 3.3077115913*m + 0.2309699292*ss,
       -1.2684380046*l + 2.6097574011*m - 0.3413193965*ss,
       -0.0041960863*l - 0.7034186147*m + 1.7076147010*ss,
    ))


def _oklch_to_rgb_gamut_mapped(lightness, chroma, hue, iterations=13):
    """Convert OKLCH to sRGB, reducing only chroma when outside gamut."""
    lightness = np.asarray(lightness, dtype=np.float64)
    chroma = np.asarray(chroma, dtype=np.float64)
    hue = np.asarray(hue, dtype=np.float64)
    low = np.zeros_like(chroma)
    high = np.maximum(chroma, 0.0)

    def convert(test_chroma):
        return _oklab_to_linear_srgb(np.column_stack((
            lightness,
            test_chroma * np.cos(hue),
            test_chroma * np.sin(hue),
        )))

    initial = convert(high)
    valid = np.all((initial >= 0.0) & (initial <= 1.0), axis=1)
    low[valid] = high[valid]
    active = ~valid
    for _ in range(int(iterations)):
        middle = (low + high) / 2.0
        trial = convert(middle)
        inside = np.all((trial >= 0.0) & (trial <= 1.0), axis=1)
        low[active & inside] = middle[active & inside]
        high[active & ~inside] = middle[active & ~inside]
    return np.clip(_encode_srgb(convert(low)), 0.0, 1.0)


def _hsluv_like_to_rgb(hue, saturation, lightness):
    """Perceptual HSL-style map using gamut-limited CIELCH.

    Hue is cyclic, saturation is radial position in the projected pole disk,
    and lightness is CIE L*. Maximum chroma is found independently for each
    hue and lightness, which is the defining practical behaviour needed from
    HSLuv for orientation mapping.
    """
    hue = np.asarray(hue, dtype=np.float64)
    saturation = np.clip(np.asarray(saturation, dtype=np.float64), 0.0, 1.0)
    lightness = np.asarray(lightness, dtype=np.float64)
    # Deliberately request a chroma beyond the sRGB gamut. The existing
    # gamut mapper finds Cmax(h, L); saturation then scales to that boundary.
    requested = np.full_like(saturation, 180.0)
    # Find Cmax by binary search in Lab, then apply radial saturation.
    low = np.zeros_like(requested)
    high = requested.copy()
    def linear_at(chroma):
        lab = np.column_stack((
            lightness,
            chroma * np.cos(hue),
            chroma * np.sin(hue),
        ))
        return _lab_to_linear_srgb(lab)
    for _ in range(14):
        middle = (low + high) / 2.0
        trial = linear_at(middle)
        valid = np.all((trial >= 0.0) & (trial <= 1.0), axis=1)
        low[valid] = middle[valid]
        high[~valid] = middle[~valid]
    chroma = low * saturation
    return np.clip(_encode_srgb(linear_at(chroma)), 0.0, 1.0)


def colours_from_projected_poles(x, y, colour_space="HSV", lightness=75.0,
                                  valid=None):
    """Map projected pole coordinates to RGB, following the MATLAB workflow."""
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.shape != y.shape:
        raise ValueError(_tr("colour.error.projected_shape"))
    if valid is None:
        valid = np.isfinite(x) & np.isfinite(y)
    else:
        valid = np.asarray(valid, dtype=bool) & np.isfinite(x) & np.isfinite(y)
    rgb = np.zeros((len(x), 3), dtype=np.uint8)
    rgb[~valid] = np.array([128, 128, 128], dtype=np.uint8)
    if not np.any(valid):
        return rgb

    xv, yv = x[valid], y[valid]
    radius = np.clip(np.hypot(xv, yv), 0.0, 1.0)
    hue = np.mod(np.arctan2(yv, xv), 2.0 * np.pi)
    space = str(colour_space).upper()
    level = float(np.clip(lightness, 0.0, 100.0))

    if space == "HSV":
        values = _hsv_to_rgb(
            hue / (2.0 * np.pi), radius,
            np.full(len(radius), level / 100.0),
        )
    elif space in ("CIELAB", "CIELCH", "CIELCHMOD"):
        # MATLAB's CIE functions receive projected x and y. Therefore a* and
        # b*, or equivalently C* and h, derive from the projected pole disk.
        if space == "CIELAB":
            chroma = 100.0 * radius
            cie_lightness = np.full(len(radius), level)
        elif space == "CIELCH":
            chroma = 85.0 * radius
            cie_lightness = np.full(len(radius), level)
        else:
            # Modified MATLAB workflow: C*=100*r and L* varies linearly
            # from 50 at the centre to the GUI value at the disk edge.
            chroma = 100.0 * radius
            cie_lightness = 50.0 + radius * (level - 50.0)
        values = _cielch_to_rgb_gamut_mapped(
            cie_lightness, chroma, hue
        )
    elif space == "OKLCH":
        # Oklab lightness uses [0, 1]. The requested edge chroma is gamut
        # mapped independently for each hue, preserving hue and lightness.
        values = _oklch_to_rgb_gamut_mapped(
            np.full(len(radius), level / 100.0),
            0.38 * radius,
            hue,
        )
    elif space == "HSLUV":
        values = _hsluv_like_to_rgb(
            hue,
            radius,
            np.full(len(radius), level),
        )
    elif space == "NONE":
        values = np.tile([0.0, 1.0, 0.0], (len(radius), 1))
    else:
        raise ValueError(_tr("colour.error.unknown_space", colour_space=colour_space))

    rgb[valid] = np.rint(255.0 * np.clip(values, 0.0, 1.0)).astype(np.uint8)
    return rgb



def cylindrical_colour_map_preview(colour_space="HSV", lightness=75.0, size=241,
                                   outside=(245, 245, 245)):
    """Create an RGB preview using the exact point-colouring function."""
    size = max(33, int(size))
    axis = np.linspace(-1.0, 1.0, size, dtype=np.float64)
    x, y = np.meshgrid(axis, -axis)
    valid = (x * x + y * y) <= 1.0
    rgb = colours_from_projected_poles(
        x.ravel(), y.ravel(), colour_space=colour_space,
        lightness=lightness, valid=valid.ravel()
    ).reshape(size, size, 3)
    rgb[~valid] = np.asarray(outside, dtype=np.uint8)
    return rgb
def colours_from_normals(normals, angles_deg, colour_space="HSV",
                         lightness=75.0, projection="Equal-angle"):
    """Return RGB and rotated normals using projected poles as colour input."""
    x, y, rotated, valid = projected_poles_from_normals(
        normals, angles_deg, projection=projection
    )
    rgb = colours_from_projected_poles(
        x, y, colour_space=colour_space, lightness=lightness, valid=valid
    )
    return rgb, rotated

