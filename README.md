<div align="center">

# 🪨 DSEpy: Discontinuity Set Extractor for CloudCompare

**A Python-based evolution of DSE for semi-automatic rock mass discontinuity analysis on 3D point clouds.**

[![Latest Release](https://img.shields.io/github/v/release/adririquelme/DSEpy?color=blue&logo=github)](https://github.com/adririquelme/DSEpy/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-CC_Runtime-3776AB?logo=python&logoColor=white)](https://www.cloudcompare.org/)
[![CloudCompare Integration](https://img.shields.io/badge/CloudCompare-Python_Plugin-00A896)](https://www.cloudcompare.org/)

[Features](#features) • [Workflow](#workflow) • [Installation](#installation) • [Documentation](#documentation) • [Citation](#citation) • [Authors](#authors)

---

</div>

<a id="overview"></a>
## 📌 Overview

**DSEpy** is an open-source Python plugin designed for **CloudCompare** to perform semi-automatic identification, classification, and geometric characterisation of rock mass discontinuity sets from 3D point clouds (LiDAR or photogrammetry).

It represents the Python/CloudCompare evolution of the original **Discontinuity Set Extractor (DSE)** software developed in MATLAB, featuring:
* Native integration with CloudCompare's 3D rendering engine and Python environment.
* High-performance processing of point cloud normal vectors.
* Advanced chromatic orientation maps for visual inspection.
* Comprehensive internationalization (i18n) support across multiple languages.

> 💡 *DSEpy allows rock engineering professionals and researchers to transition seamlessly from 3D raw point clouds to structured structural geological data.*

---

<a id="features"></a>
## 🚀 Key Features

* **🎨 Advanced Normal Colour Optimisation:** Color-code point cloud normal vectors using advanced color spaces (**HSV**, **CIELAB**, **CIELCH**, **OKLCH**, **HSLuv**, etc.) for intuitive visual orientation inspection.
* **📊 Stereonet Analysis & Pole Density:** Identify principal discontinuity set poles using spherical density calculations on stereonets.
* **🏷️ Automated Set Classification:** Classify 3D points based on proximity to main set orientations.
* **🔍 Spatial Clustering & Geometric Extraction:**
  * Choose the existing custom KDTree DBSCAN or HDBSCAN (requires optional scikit-learn 1.3.0+ in CloudCompare's Python environment).
  * **Normal Spacing:** Compute true normal spacing between adjacent surfaces within a set.
  * **Persistence:** Calculate discontinuity persistence and extent.
  * **Fisher Analysis:** Statistical evaluation of orientation dispersion.
  * **Cluster Facets:** Extract individual 3D surface facets for geomechanical mapping.
* **🌐 Multi-Language Support (i18n):** Native internationalization with JSON-based translation dictionaries (`locales/`).

---

<a id="workflow"></a>
## 🔄 Workflow

```text
 ┌────────────────────────────────────────┐
 │   3D Point Cloud + Normals (CloudCompare)
 └───────────────────┬────────────────────┘
                     │
                     ▼
 ┌────────────────────────────────────────┐
 │  1. Normal Colour Optimisation & Poles │ ──> Interactive Stereonet Density Maps
 └───────────────────┬────────────────────┘
                     │
                     ▼
 ┌────────────────────────────────────────┐
 │  2. Discontinuity Set Classification   │ ──> Angle Thresholding & Set Assignment
 └───────────────────┬────────────────────┘
                     │
                     ▼
 ┌────────────────────────────────────────┐
 │  3. Spatial Clustering & Geometry      │
 ├────────────────────────────────────────┤
 │  • Spacing Calculation                 │
 │  • Persistence Estimation              │
 │  • Fisher Analysis                     │
 │  • Cluster Facet Extraction            │
 └────────────────────────────────────────┘
```

---

<a id="installation"></a>
## 🛠️ Installation & Setup

### Prerequisites
* **[CloudCompare](https://www.cloudcompare.org/)** installed with its **Python Runtime** component enabled. If it was omitted, rerun the CloudCompare installer in modify mode and add it. DSEpy must run in the Python environment provided by CloudCompare; installing a separate system Python is not a substitute.
* DSEpy supports stable and beta Python runtimes: runtimes that expose normal accessors read normals directly; on stable runtimes that do not, use **Edit → Normals → Export normals to SF(s)** to create `Nx`, `Ny`, and `Nz` first.

---

#### 1. Download DSEpy
Git is optional. Choose either method:

* **Without Git:** open [DSEpy Releases](https://github.com/adririquelme/DSEpy/releases), choose the version you want, and download its **Source code (zip)** archive. Extract it and keep the complete folder structure (including `icons` and `locales`). To use the current development branch instead, select **Code → Download ZIP** on the repository page.
* **With Git:**
```bash
git clone https://github.com/adririquelme/DSEpy.git C:\CCPlugins\DSEPy
```

Place the extracted or cloned folder somewhere permanent, for example `C:\CCPlugins\DSEpy`. In the steps below, replace that example with the actual folder path if different.

#### 2. Install Dependencies in CloudCompare's Python Runtime
Packages must be installed for the Python interpreter used by CloudCompare, not by running a bare `pip` command (which may target another Python installation).

1. Open CloudCompare, open its Python Console, and run:
   ```python
   import sys
   print(sys.version)
   print(sys.executable)
   ```
2. Close CloudCompare completely. Locate the `python.exe` installed with the CloudCompare Python Runtime. If `sys.executable` printed the path to that `python.exe`, use it. If it printed `CloudCompare.exe` (or another host executable), do **not** use that path with `-m pip`; find the Runtime's `python.exe` inside the CloudCompare installation folder instead. Its location varies between versions and installation folders.
3. In PowerShell, substitute the actual paths in this command:
   ```powershell
   & "C:\Path\To\CloudCompare\PythonRuntime\python.exe" -m pip install --user -r "C:\CCPlugins\DSEpy\requirements.txt"
   ```
   `-m pip` ensures pip belongs to that interpreter. `--user` installs packages for the current Windows user and normally avoids writing to the protected `Program Files` directory.

If PowerShell reports that pip is missing, first check that the selected executable really is the CloudCompare Runtime's `python.exe` and that the Runtime is installed. Do not work around this by installing packages into an unrelated system Python.

---

#### 3. Quick Start / Launching DSEpy
1. Open **CloudCompare**.
2. Open the **Python Console** (from the menu or toolbar).
3. Execute the launcher script, replacing the example path if needed:
   ```python
   exec(open(r"C:\CCPlugins\DSEpy\main_gui.py", encoding="utf-8").read())
   ```

---

<a id="repository-structure"></a>
## 📂 Repository Structure

```text
DSEpy/
├── main_gui.py          # Main GUI launcher & CloudCompare interface
├── colour_optimisation.py   # Chromatic space algorithms & normal colour-coding
├── stereonet.py             # Stereographic projection & density computations
├── i18n.py                  # Internationalization translation engine
├── requirements.txt         # Python package dependencies
├── CITATION.cff             # Academic citation metadata
├── CHANGELOG.md             # Version history
├── LICENSE                  # GNU GPL v3.0 License
├── docs/                    # Complete user & developer documentation
│   ├── installation.md
│   ├── user_guide.md
│   ├── workflow.md
│   └── troubleshooting.md
├── icons/                   # GUI icons & visual assets
└── locales/                 # i18n translation JSON files (en, es, ca, de, etc.)
```

---

<a id="documentation"></a>
## 📚 Documentation

The complete DSEpy documentation is available in the project Wiki:

👉 **[DSEpy Wiki](https://github.com/adririquelme/DSEPy/wiki/)**

The Wiki is the primary source of documentation for DSEpy and is continuously updated as new features are implemented.

### Available Documentation

* 📖 **User Guide**
  * Detailed walkthrough of all graphical interfaces.
  * Step-by-step workflows.
  * Parameter descriptions and recommended settings.

* 📊 **Stereonet Analysis & Principal Pole Identification**
  * Lower-hemisphere projection methods.
  * Pole density estimation.
  * Kernel Density Estimation (KDE).
  * Principal pole detection and filtering algorithms.

* 🏷️ **Set Classification**
  * Automatic discontinuity set assignment.
  * Angular thresholding methodology.
  * Colour-coded classification workflows.

* 🔍 **Clustering & Facets**
  * Spatial clustering of classified discontinuities.
  * Persistence estimation.
  * Normal spacing calculations.
  * Fisher statistics.
  * 3D facet extraction and analysis.

* ⚙️ **Methodological Background**
  * Mathematical foundations.
  * Structural geology concepts.
  * Projection geometry.
  * Implemented algorithms and assumptions.

* 🔧 **Installation & Troubleshooting**
  * Installation procedures.
  * Dependency management.
  * Common CloudCompare Python issues.
  * Frequently Asked Questions (FAQs).

* 📚 **Scientific References**
  * Original DSE methodology papers.
  * DSEpy methodological developments.
  * Stereographic projection references.
  * Rock mechanics and structural geology bibliography.

### Quick Access

| Section | Description |
|----------|-------------|
| **Home** | Documentation entry point and navigation hub |
| **Stereonet Analysis & Principal Pole Identification** | Pole density estimation and stereonet analysis |
| **Set Classification** | Discontinuity family assignment workflow |
| **Clustering & Facets** | Spatial clustering and geometric characterisation |
| **References** | Scientific and methodological bibliography |

➡️ **Open the Wiki:** [https://github.com/adririquelme/DSEPy/wiki](https://github.com/adririquelme/DSEPy/wiki)

---

<a id="authors"></a>
## 👥 Authors & Acknowledgments

**DSEpy** is developed and maintained by:

* **Adrián Riquelme Guill** [![ORCID](https://img.shields.io/badge/ORCID-0000--0002--2155--3515-green?logo=orcid&logoColor=white)](https://orcid.org/0000-0002-2155-3515) — *Department of Civil Engineering, Universidad de Alicante*
* **Roberto Tomás Jover** [![ORCID](https://img.shields.io/badge/ORCID-0000--0003--2947--9441-green?logo=orcid&logoColor=white)](https://orcid.org/0000-0003-2947-9441) — *Department of Civil Engineering, Universidad de Alicante*
* **Antonio Abellán Fernández** [![ORCID](https://img.shields.io/badge/ORCID-0000--0003--2391--6049-green?logo=orcid&logoColor=white)](https://orcid.org/0000-0003-2391-6049)

---

<a id="citation"></a>
## 🎓 Citation

If you use **DSEpy** in academic research, publications, or commercial projects, please cite both the underlying methodology publications and the software implementation:

### 1. General DSE Methodology & Joint Recognition
> **Riquelme, A. J., Abellán, A., Tomás, R., & Jaboyedoff, M.** (2014). *A new approach for semi-automatic rock mass joints recognition from 3D point clouds*. Computers & Geosciences, 68, 38–52. https://doi.org/10.1016/j.cageo.2014.03.014

```bibtex
@article{Riquelme2014,
  author  = {Riquelme, A. J. and Abell{\'a}n, A. and Tom{\'a}s, R. and Jaboyedoff, M.},
  title   = {A new approach for semi-automatic rock mass joints recognition from 3D point clouds},
  journal = {Computers \& Geosciences},
  volume  = {68},
  pages   = {38--52},
  year    = {2014},
  doi     = {10.1016/j.cageo.2014.03.014}
}
```

### 2. Methodological Foundations (PhD Thesis)
> **Riquelme, A.** (2015). *Uso de nubes de puntos 3D para identificación y caracterización de familias de discontinuidades planas en afloramientos rocosos y evaluación de la calidad geomecánica* [Doctoral dissertation, Universidad de Alicante]. RUA Repository. https://rua.ua.es/entities/publication/78d254b9-1a7b-49b1-a35a-c0edbdeeb225

```bibtex
@phdthesis{Riquelme2015Thesis,
  author = {Riquelme, Adri{\'a}n},
  title  = {Uso de nubes de puntos 3D para identificación y caracterización de familias de discontinuidades planas en afloramientos rocosos y evaluación de la calidad geomecánica},
  school = {Universidad de Alicante},
  year   = {2015},
  url    = {[https://rua.ua.es/entities/publication/78d254b9-1a7b-49b1-a35a-c0edbdeeb225](https://rua.ua.es/entities/publication/78d254b9-1a7b-49b1-a35a-c0edbdeeb225)}
}
```

### 3. Normal Spacing Analysis Method
> **Riquelme, A., Abellán, A., & Tomás, R.** (2015). *Discontinuity spacing analysis in rock masses using 3D point clouds*. Engineering Geology, 195, 185–195. https://doi.org/10.1016/j.enggeo.2015.06.009

```bibtex
@article{Riquelme2015Spacing,
  author  = {Riquelme, A. and Abell{\'a}n, A. and Tom{\'a}s, R.},
  title   = {Discontinuity spacing analysis in rock masses using 3D point clouds},
  journal = {Engineering Geology},
  volume  = {195},
  pages   = {185--195},
  year    = {2015},
  doi     = {10.1016/j.enggeo.2015.06.009}
}
```

### 4. Persistence Estimation Method
> **Riquelme, A., Tomás, R., Cano, M., Pastor, J. L., & Abellán, A.** (2018). *Automatic Mapping of Discontinuity Persistence on Rock Masses Using 3D Point Clouds*. Rock Mechanics and Rock Engineering, 51(10), 3005–3028. https://doi.org/10.1007/s00603-018-1519-9

```bibtex
@article{Riquelme2018Persistence,
  author  = {Riquelme, A. and Tom{\'a}s, R. and Cano, M. and Pastor, J. L. and Abell{\'a}n, A.},
  title   = {Automatic Mapping of Discontinuity Persistence on Rock Masses Using 3D Point Clouds},
  journal = {Rock Mechanics and Rock Engineering},
  volume  = {51},
  number  = {10},
  pages   = {3005--3028},
  year    = {2018},
  doi     = {10.1007/s00603-018-1519-9}
}
```

### 5. Normal Vector Colour Mapping & Density Analysis
> **Riquelme, A., Tomás, R., Cano, M., Pastor, J. L., & Abellán, A.** (2026). *Orientation-based colour mapping and spherical density analysis for rock discontinuity detection in 3D point clouds of roadcut slopes*. Journal of Rock Mechanics and Geotechnical Engineering. https://doi.org/10.1016/j.jrmge.2025.12.059

```bibtex
@article{Riquelme2026Colour,
  author  = {Riquelme, A. and Tom{\'a}s, R. and Cano, M. and Pastor, J. L. and Abell{\'a}n, A.},
  title   = {Orientation-based colour mapping and spherical density analysis for rock discontinuity detection in 3D point clouds of roadcut slopes},
  journal = {Journal of Rock Mechanics and Geotechnical Engineering},
  year    = {2026},
  doi     = {10.1016/j.jrmge.2025.12.059}
}
```

### 6. DSEpy Software Implementation
> **Riquelme, A., Tomás, R., & Abellán, A.** (2026). *DSEpy: Python-based Discontinuity Set Extractor for CloudCompare* (Version 1.0.1). GitHub. https://github.com/adririquelme/DSEpy

```bibtex
@software{Riquelme_DSEpy_2026,
  author    = {Riquelme, Adri{\'a}n and Tom{\'a}s, Roberto and Abell{\'a}n, Antonio},
  title     = {{DSEpy: Python-based Discontinuity Set Extractor for CloudCompare}},
  year      = {2026},
  version   = {1.0.1},
  publisher = {GitHub},
  url       = {[https://github.com/adririquelme/DSEpy](https://github.com/adririquelme/DSEpy)}
}
```

*You can also export citation formats directly from the [`CITATION.cff`](CITATION.cff) file on GitHub.*

---

<a id="license"></a>
## 📄 License

Distributed under the **GNU General Public License v3.0 (GPL-3.0)**. See [`LICENSE`](LICENSE) for more details. Compatible with the open-source CloudCompare ecosystem.
