import numpy as np
import pytest

pytest.importorskip("sklearn")

from spectral_clustering import (  # noqa: E402
    affinity_matrix,
    orientations_to_vectors,
    spectral_clustering_discontinuities,
    vectors_to_orientations,
)

CENTERS = [(30.0, 20.0), (150.0, 60.0), (270.0, 35.0)]


def _synthetic(n=40, noise=3.0, seed=1):
    rng = np.random.default_rng(seed)
    data, truth = [], []
    for i, (t, p) in enumerate(CENTERS):
        data.append(np.column_stack((t + rng.normal(0, noise, n),
                                     p + rng.normal(0, noise, n))))
        truth += [i] * n
    return np.vstack(data), np.array(truth)


def _same_partition(a, b):
    pairs = set(zip(a.tolist(), b.tolist()))
    return len(pairs) == len(set(a.tolist())) == len(set(b.tolist()))


def test_vector_roundtrip():
    o = np.array([[30.0, 20.0], [200.0, 70.0]])
    np.testing.assert_allclose(
        vectors_to_orientations(orientations_to_vectors(o)), o, atol=1e-9)
    assert np.allclose(np.linalg.norm(orientations_to_vectors(o), axis=1), 1)


def test_affinity_properties():
    a = affinity_matrix(orientations_to_vectors(_synthetic()[0]))
    assert np.allclose(a, a.T) and np.all(np.diag(a) == 0)


def test_known_k_recovers_families():
    data, truth = _synthetic()
    res = spectral_clustering_discontinuities(data, k=3)
    assert res.u_matrix.shape == (len(data), 3)
    assert np.allclose(np.linalg.norm(res.u_matrix, axis=1), 1)
    assert _same_partition(res.labels, truth)
    for t, p in CENTERS:
        d = np.abs(res.mean_vectors - [t, p]).sum(axis=1).min()
        assert d < 5


@pytest.mark.parametrize("method", ["eigengap", "silhouette"])
def test_auto_k(method):
    data, truth = _synthetic()
    res = spectral_clustering_discontinuities(data, k_method=method)
    assert res.k_optimal == 3
    assert _same_partition(res.labels, truth)


def test_cluster_normals_subsampling():
    from spectral_clustering import cluster_normals

    data, truth = _synthetic(n=100)
    res, labels = cluster_normals(orientations_to_vectors(data), k=3, max_samples=90)
    assert len(labels) == len(data) and len(res.labels) == 90
    assert _same_partition(labels, truth)


def test_progress_and_cancel():
    from spectral_clustering import SpectralClusteringCancelled

    data, _ = _synthetic(n=30)
    calls = []
    spectral_clustering_discontinuities(
        data, k=3, progress=lambda p, m: calls.append(p) or True)
    assert calls == sorted(calls) and calls[-1] >= 85
    with pytest.raises(SpectralClusteringCancelled):
        spectral_clustering_discontinuities(data, k=3, progress=lambda p, m: False)


def test_invalid_input():
    with pytest.raises(ValueError):
        spectral_clustering_discontinuities(np.zeros((10, 3)))
