"""Spectral clustering of rock discontinuity sets.

Implements the method of Jimenez-Rodriguez & Sitar (2006), "A spectral method
for clustering of rock discontinuity sets", Int. J. Rock Mech. Min. Sci. 43.

Orientations are (trend, plunge) pairs in degrees, plunge measured towards the
lower hemisphere. The tool is meant to run after the colour-rotation
optimisation step and accepts either original or rotated orientations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

DEFAULT_SIGMA = 0.12
SIGMA_RANGE = (0.10, 0.15)

# Callback(percent, message) -> False requests cancellation.
ProgressCallback = Callable[[float, str], bool]


class SpectralClusteringCancelled(Exception):
    """Raised when the progress callback requests cancellation."""


def _report(progress: Optional[ProgressCallback], percent: float, message: str) -> None:
    if progress is not None and progress(percent, message) is False:
        raise SpectralClusteringCancelled()


@dataclass
class SpectralClusteringResult:
    """Result of :func:`spectral_clustering_discontinuities`.

    Attributes:
        labels: Cluster label (0..K-1) per input orientation, shape (N,).
        k_optimal: Number of families used.
        mean_vectors: Mean orientation per family as (trend, plunge) in
            degrees, shape (K, 2).
        u_matrix: Row-normalised eigenvector matrix U, shape (N, K).
        eigenvalues: Eigenvalues of L in descending order.
        sigma: Scale parameter used.
        silhouette: Silhouette score of the partition in U space, or None.
    """

    labels: np.ndarray
    k_optimal: int
    mean_vectors: np.ndarray
    u_matrix: np.ndarray
    eigenvalues: np.ndarray
    sigma: float
    silhouette: Optional[float] = None


def orientations_to_vectors(orientations: np.ndarray) -> np.ndarray:
    """Convert (trend, plunge) in degrees to unit vectors.

    Args:
        orientations: Array of shape (N, 2) with [trend, plunge] in degrees.

    Returns:
        Array of shape (N, 3) of unit vectors (x1, x2, x3).
    """
    arr = np.asarray(orientations, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError("orientations must have shape (N, 2) [trend, plunge]")
    a, b = np.radians(arr[:, 0]), np.radians(arr[:, 1])
    return np.column_stack(
        (np.cos(a) * np.cos(b), np.sin(a) * np.cos(b), np.sin(b))
    )


def vectors_to_orientations(vectors: np.ndarray) -> np.ndarray:
    """Convert unit vectors to lower-hemisphere (trend, plunge) in degrees.

    Args:
        vectors: Array of shape (N, 3).

    Returns:
        Array of shape (N, 2) with trend in [0, 360) and plunge in [0, 90].
    """
    v = np.asarray(vectors, dtype=float).copy()
    v[v[:, 2] < 0] *= -1.0
    trend = np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 360.0
    plunge = np.degrees(np.arcsin(np.clip(v[:, 2], -1.0, 1.0)))
    return np.column_stack((trend, plunge))


def affinity_matrix(vectors: np.ndarray, sigma: float = DEFAULT_SIGMA) -> np.ndarray:
    """Build the affinity matrix A with d^2 = 1 - (xi . xj)^2.

    Args:
        vectors: Unit vectors, shape (N, 3).
        sigma: Gaussian scale parameter.

    Returns:
        Symmetric (N, N) matrix with zero diagonal.
    """
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    dots = vectors @ vectors.T
    d2 = np.clip(1.0 - dots**2, 0.0, None)
    a = np.exp(-d2 / (2.0 * sigma**2))
    np.fill_diagonal(a, 0.0)
    return a


def normalized_affinity(a: np.ndarray) -> np.ndarray:
    """Return L = D^-1/2 A D^-1/2.

    Args:
        a: Affinity matrix (N, N).

    Returns:
        Normalised affinity matrix L.
    """
    deg = a.sum(axis=1)
    inv_sqrt = np.zeros_like(deg)
    nz = deg > 0
    inv_sqrt[nz] = 1.0 / np.sqrt(deg[nz])
    return a * inv_sqrt[:, None] * inv_sqrt[None, :]


def _row_normalised_top_eigvecs(eigvecs: np.ndarray, k: int) -> np.ndarray:
    v = eigvecs[:, :k]
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return v / norms


def _eigengap_k(eigvals: np.ndarray, k_min: int, k_max: int) -> int:
    """K* = argmax_k (lambda_k - lambda_{k+1}), k in [k_min, k_max]."""
    k_max = min(k_max, len(eigvals) - 1)
    ks = np.arange(k_min, k_max + 1)
    gaps = eigvals[ks - 1] - eigvals[ks]
    return int(ks[np.argmax(gaps)])


def mean_orientations(vectors: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    """Axial mean orientation of each family (dominant eigenvector of T).

    Args:
        vectors: Unit vectors (N, 3).
        labels: Labels (N,).
        k: Number of families.

    Returns:
        Array (K, 2) of (trend, plunge) in degrees; NaN for empty families.
    """
    means = np.full((k, 3), np.nan)
    for c in range(k):
        members = vectors[labels == c]
        if len(members) == 0:
            continue
        _, vecs = np.linalg.eigh(members.T @ members)
        means[c] = vecs[:, -1]
    out = np.full((k, 2), np.nan)
    ok = ~np.isnan(means[:, 0])
    out[ok] = vectors_to_orientations(means[ok])
    return out


def spectral_clustering_discontinuities(
    orientations: np.ndarray,
    k: Optional[int] = None,
    sigma: float = DEFAULT_SIGMA,
    k_max: int = 8,
    k_method: str = "eigengap",
    n_init: int = 10,
    random_state: Optional[int] = 0,
    progress: Optional[ProgressCallback] = None,
) -> SpectralClusteringResult:
    """Cluster discontinuity orientations into sets via spectral clustering.

    Args:
        orientations: Array (N, 2) of [trend, plunge] in degrees.
        k: Number of families. If None it is chosen automatically.
        sigma: Affinity scale (default 0.12, typical range 0.10-0.15).
        k_max: Upper bound for automatic K selection.
        k_method: "eigengap" or "silhouette" (used when k is None).
        n_init: Number of K-means random restarts.
        random_state: Seed for K-means.
        progress: Optional callback(percent, message); return False to cancel.

    Returns:
        A :class:`SpectralClusteringResult`.

    Raises:
        ValueError: On invalid input shapes or parameters.
        SpectralClusteringCancelled: If the callback requests cancellation.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    x = orientations_to_vectors(orientations)
    n = x.shape[0]
    if n < 3:
        raise ValueError("at least 3 orientations are required")
    if k_method not in ("eigengap", "silhouette"):
        raise ValueError("k_method must be 'eigengap' or 'silhouette'")
    if k is not None and not 1 <= k <= n:
        raise ValueError("k must be between 1 and N")

    _report(progress, 5, f"Building affinity matrix ({n} x {n})")
    a = affinity_matrix(x, sigma)
    _report(progress, 20, "Normalised Laplacian L = D^-1/2 A D^-1/2")
    lap = normalized_affinity(a)
    _report(progress, 30, "Eigendecomposition of L (this can take a while)")
    w, v = np.linalg.eigh(lap)
    _report(progress, 60, "Eigenvalues sorted")
    order = np.argsort(w)[::-1]
    eigvals, eigvecs = w[order], v[:, order]

    def run(kk: int):
        u = _row_normalised_top_eigvecs(eigvecs, kk)
        km = KMeans(n_clusters=kk, n_init=n_init, random_state=random_state)
        return u, km.fit_predict(u)

    if k is None:
        upper = min(k_max, n - 1)
        if upper < 2:
            raise ValueError("not enough points for automatic K selection")
        if k_method == "eigengap":
            _report(progress, 65, "Selecting K by eigengap")
            k = _eigengap_k(eigvals, 2, upper)
        else:
            best = -np.inf
            for kk in range(2, upper + 1):
                _report(progress, 62 + 18.0 * (kk - 2) / max(1, upper - 1),
                        f"Silhouette for K={kk}")
                u_k, lab = run(kk)
                if len(np.unique(lab)) < 2:
                    continue
                s = silhouette_score(u_k, lab)
                if s > best:
                    best, k = s, kk
            if k is None:
                k = 2

    _report(progress, 85, f"K-means in spectral space (K={k})")
    u, labels = run(k)
    _report(progress, 95, "Computing mean orientations")
    sil = None
    if 2 <= k < n and len(np.unique(labels)) >= 2:
        sil = float(silhouette_score(u, labels))

    return SpectralClusteringResult(
        labels=labels,
        k_optimal=int(k),
        mean_vectors=mean_orientations(x, labels, k),
        u_matrix=u,
        eigenvalues=eigvals,
        sigma=float(sigma),
        silhouette=sil,
    )


def cluster_normals(
    normals: np.ndarray,
    k: Optional[int] = None,
    max_samples: int = 3000,
    seed: int = 0,
    progress: Optional[ProgressCallback] = None,
    **kwargs,
) -> tuple[SpectralClusteringResult, np.ndarray]:
    """Spectral clustering of many normals, subsampling large inputs.

    The affinity matrix is O(N^2), so at most ``max_samples`` normals are used
    to build the spectral embedding. Remaining normals are assigned to the
    family whose mean axis is closest (largest |x . m|). Mean orientations are
    then recomputed from all normals.

    Args:
        normals: Finite, non-zero vectors of shape (N, 3).
        k: Number of families or None for automatic selection.
        max_samples: Maximum number of points in the spectral step.
        seed: Seed for subsampling and K-means.
        progress: Optional callback(percent, message); return False to cancel.
        **kwargs: Forwarded to :func:`spectral_clustering_discontinuities`.

    Returns:
        Tuple (result, labels) where labels has one entry per input normal.
        ``result.u_matrix`` and ``result.labels`` refer to the sampled points.
    """
    vec = np.asarray(normals, dtype=float)
    vec = vec / np.linalg.norm(vec, axis=1, keepdims=True)
    n = len(vec)
    if n > max_samples:
        idx = np.sort(np.random.default_rng(seed).choice(n, max_samples, replace=False))
    else:
        idx = np.arange(n)
    _report(progress, 0, f"Using {len(idx)} of {n} poles for the spectral step")

    def scaled(percent: float, message: str) -> bool:
        return progress is None or progress(2 + 0.88 * percent, message) is not False

    result = spectral_clustering_discontinuities(
        vectors_to_orientations(vec[idx]), k=k, random_state=seed,
        progress=scaled, **kwargs
    )
    if n == len(idx):
        _report(progress, 100, "Done")
        return result, result.labels

    _report(progress, 92, f"Assigning remaining {n - len(idx)} poles to sets")
    means = orientations_to_vectors(np.nan_to_num(result.mean_vectors))
    labels = np.argmax(np.abs(vec @ means.T), axis=1)
    labels[idx] = result.labels
    result.mean_vectors = mean_orientations(vec, labels, result.k_optimal)
    _report(progress, 100, "Done")
    return result, labels


SpectralClusteringTool = spectral_clustering_discontinuities

