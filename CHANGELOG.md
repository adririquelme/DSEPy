# Changelog

All notable changes to DSEPy are documented in this file.

## [Unreleased] - 1.0.3beta

### Added

- Spectral Clustering tool (Tools menu) implementing Jimenez-Rodriguez & Sitar (2006), with original/rotated analysis space, automatic K selection (eigengap or silhouette), optional legend and centroid orientations reported in the original space.
- Tooltips for the Tools menu entries.

### Changed

- Tools menu order: Normal Colour Optimisation, Spectral Clustering, Normal Spacing, Persistence.
- Compact main window: smaller minimum heights for tables, pole-editing buttons moved next to the manual entry fields, shorter execution log and a vertically scrollable workflow panel for small screens.

## [1.0.2] - 2026-10-05

### Fixed

- Detect point-cloud normal access according to the capabilities exposed by the active CloudCompare Python runtime.
- Support stable `pycc` builds by reading normals from the `Nx`, `Ny`, and `Nz` scalar fields exported by CloudCompare.
- Show a one-time compatibility notice when the selected cloud has normals that the active runtime cannot read directly.
- Reduce the Refresh control size and increase the visible execution log height.
- Update the installation guide to use the current `main_gui.py` launcher.

## [1.0.0] - 2026-09-13

### Added

- First public release of DSEPy.
- Principal pole extraction and review workflow.
- Spherical/steronet density analysis of discontinuity poles.
- 3D point-cloud colour coding based on pole orientations.
- Original and rotated pole spaces for orientation-based colour mapping.
- Normal Colour Optimisation using differential-evolution-based rotation optimisation.
- Discontinuity-set (DS) classification.
- Spatial clustering of discontinuities using DBSCAN-based analysis.
- Fisher directional-statistics analysis of cluster normals.
- Planar cluster/facet generation with multiple facet shapes.
- Normal spacing and persistence analysis tools.
- Stereonet plotting and density visualisation.
- CloudCompare scalar-field export and family/cluster cloud generation.
- Multilingual graphical user interface and translated tooltips/log messages.
- Persistent execution logging for post-run verification and troubleshooting.

### Notes

- DSEPy 1.0.0 is distributed as Python source code for use with CloudCompare's Python/`pycc` environment.
- This release does not package CloudCompare itself or redistribute third-party Python dependencies.
