# Changelog

All notable changes to DSEPy are documented in this file.

## [Unreleased] - 1.0.3beta

### Added

- Technical report generator (Tools → Technical Report...): produces a self-contained HTML and/or Markdown report (English or Spanish) with project metadata, colour optimisation, principal poles, assignment, clustering, spacing and persistence results, parameters, equations and figures (`report_generator.py`).
- Spectral Clustering tool (Tools menu) implementing Jimenez-Rodriguez & Sitar (2006), with original/rotated analysis space, automatic K selection (eigengap or silhouette), optional legend and centroid orientations reported in the original space.
- Tooltips for the Tools menu entries.
- Technical report: A4-oriented layout (figures scaled to the text width, equations at a readable size), a "where:" legend defining every variable after each equation, and a new menu icon (`icons/technical_report.png`).
- Technical report metadata (client, location, author, version, observations, output folder and format) is remembered in the local settings between sessions.
- Normal Colour Optimisation: live dip histogram (original vs. current rotation) updated at each generation, shown above the status text.
- Automatic persistence in the point-cloud metadata (`DSE_State`): the colour rotation and the principal poles are saved after each step and restored automatically when the cloud is selected, if the point count is unchanged. Only kept when the cloud is saved as `.bin` or in a project. Spacing, persistence and Step 3 results are not stored. A restored cloud counts as having completed Step 1: the technical report recomputes the Step 1 density and stereonets on demand from the restored poles, and if the poles were already classified (the Discontinuity Set field is in the cloud and no pole was edited afterwards) Step 2 is also considered done, its report section is rebuilt and Step 3 is enabled.
- About window shows "Discontinuity Set Extractor (DSE)" and its version.
- Technical report: the units of all distances are stated as those of the point cloud, and a final "Disclaimer and responsibility" section states the software is provided without warranty and the user is responsible for the results. The same disclaimer is shown in the About window.
- Technical report: the fitted-planes figure now reproduces the "Plot stereonet" figure of the Fisher tab: cluster normals per set (not assumed parallel), mean pole, circle of maximum deviation and 95 % confidence circle of the mean pole.
- Technical report: the identification section now describes the analysed point cloud: number of points and axis-aligned bounding box (minimum, maximum, centre and dimensions).
- Technical report: new "Mean block size (Palmström)" section after the normal spacing analysis. All combinations of three sets are evaluated (J1-J2-J3, J1-J2-J4, J1-J3-J4, J2-J3-J4… for four or more sets) and each combination is listed explicitly; each gets V_b = s1·s2·s3 / (sin γ12 · sin γ13 · sin γ23) and d_b = V_b^(1/3) for three scenarios documented in the text: pessimistic (μ + 1.645σ, upper tail), average (μ) and conservative (max(μ − σ, minimum spacing), lower tail). Skipped when fewer than three sets have spacing results.

### Fixed

- The "Show density" button is enabled for a cloud restored with saved principal poles; the pole density (original and rotated) is computed on first use from the restored poles and parameters, so the density stereonet with the families can be drawn without repeating the automatic analysis.
- Technical report: the original-poles coloured stereonet now uses the Riquelme stereonet with labels and colours computed from its own original projection (previously the rotated colours were used).
- Normal spacing failed with "module 'numpy' has no attribute 'trapezoid'" on NumPy < 2.0; a compatible `trapz` fallback is used.
- The Spectral Clustering and Plot Poles figures no longer block the interface, so the pole density figure opens while they are open.

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
