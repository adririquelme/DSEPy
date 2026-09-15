<div align="center">

# 🪨 DSEpy: Discontinuity Set Extractor for CloudCompare

**A Python-based evolution of DSE for semi-automatic rock mass discontinuity analysis on 3D point clouds.**

[![Latest Release](https://img.shields.io/github/v/release/adririquelme/DSEpy?color=blue&logo=github)](https://github.com/adririquelme/DSEpy/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![CloudCompare Integration](https://img.shields.io/badge/CloudCompare-Python_Plugin-00A896)](https://www.cloudcompare.org/)

[Features](#features) • [Workflow](#workflow) • [Installation](#installation) • [Documentation](#documentation) • [Citation](#citation) • [Authors](#authors)

---

</div>

<a id="overview"></a>
## 📌 Overview

**DSEpy** is an open-source Python plugin designed for **CloudCompare** to perform semi-automatic identification, classification, and geometric characterisation of rock mass discontinuity sets from 3D point clouds (LiDAR or photogrammetry).

It represents the Python/CloudCompare evolution of the original **Discontinuity Set Extractor (DSE)** software developed in MATLAB, featuring:
* Native integration with CloudCompare's 3D rendering and Python environment.
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
  * **Normal Spacing:** Compute true spacing between adjacent surfaces within a set.
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
## 🛠️ Installation & Requirements

### Prerequisites
* **[CloudCompare](https://www.cloudcompare.org/)** (v2.12 or higher recommended).
* **CloudCompare Python Plugin** enabled.

### Installing Dependencies in CloudCompare's Python

Since DSEpy runs within CloudCompare's embedded Python environment, dependencies must be installed into CloudCompare's specific Python interpreter, not the system-wide Python.

1. **Find CloudCompare's Python executable:**
   Open CloudCompare, open the **Python Console**, and run:
   ```python
   import sys
   print(sys.executable)
   ```
2. **Install dependencies:**
   Open Windows Command Prompt (CMD) or PowerShell and use that specific path to install the packages:
   ```cmd
   "C:\Path\To\CloudCompare\python.exe" -m pip install -r requirements.txt
   ```
   *Alternatively, run this inside CloudCompare's Python console:*
   ```python
   import subprocess, sys
   subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy", "scipy", "matplotlib", "Pillow"])
   ```

### Quick Start
1. Clone this repository or download the [Latest Release ZIP](https://github.com/adririquelme/DSEpy/releases):
   ```bash
   git clone [https://github.com/adririquelme/DSEpy.git](https://github.com/adririquelme/DSEpy.git)
   ```
2. Keep `icons/` and `locales/` in the same root folder as `main_gui_v100.py`.
3. Open **CloudCompare**, open the **Python Console**, and launch DSEpy:
   ```python
   exec(open("path/to/main_gui_v100.py").read())
   ```

---

<a id="repository-structure"></a>
## 📂 Repository Structure

```text
DSEpy/
├── main_gui_v100.py          # Main GUI launcher & CloudCompare interface
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

For in-depth guides and technical details, consult the [`docs/`](./docs) folder:
* 📥 **[Installation Guide](./docs/installation.md):** Step-by-step environment setup.
* 📖 **[User Guide](./docs/user_guide.md):** Detailed GUI walkthrough and parameter configuration.
* ⚙️ **[Methodological Workflow](./docs/workflow.md):** Scientific background and algorithms.
* 🔧 **[Troubleshooting](./docs/troubleshooting.md):** Common errors, logs (`DSE_execution_log.txt`), and FAQs.

---

<a id="authors"></a>
## 👥 Authors & Acknowledgments

**DSEpy** is developed and maintained by:
* **Adrián Riquelme Guill** — *Department of Civil Engineering, Universidad de Alicante*
* **Roberto Tomás Jover** — *Department of Civil Engineering, Universidad de Alicante*
* **Antonio Abellán Fernández**

---

<a id="citation"></a>
## 🎓 Citation

If you use **DSEpy** in academic research, publications, or commercial projects, please cite both the underlying methodology article and the software implementation:

### 1. Original Methodology Paper
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

### 2. DSEpy Software Implementation
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
