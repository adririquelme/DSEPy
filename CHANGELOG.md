# Changelog

All notable changes to DSEPy are documented in this file.

## [1.0.2]
 
### Added
 
- New cluster analysis functionality for discontinuity data interpretation.
- Alternative normal vector loading using scalar fields (`Nx`, `Ny`, `Nz`) when direct access through the CloudCompare Python API is unavailable.
 
### Improved
 
- Better compatibility across CloudCompare versions.
- More robust handling of normal vector information.
- Improved user feedback when normals cannot be accessed directly.
 
### Fixed
 
- Several minor bugs and stability issues.
- Minor GUI improvements and code cleanup.

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
