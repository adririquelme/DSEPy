<div align="center">

# 🪨 DSEpy: Discontinuity Set Extractor for CloudCompare

**A Python-based evolution of DSE for semi-automatic rock mass discontinuity analysis on 3D point clouds.**

https://img.shields.io/github/v/release/adririquelme/DSEPy?color=blue&logo=github](https://github.com/adririquelme/DSEPy/releases)
https://img.shields.io/badge/License-GPLv3-blue.svg](https://www.gnu.org/licenses/gpl-3.0)
[!tps://img.shields.io/badge/Python-CloudCompare%20Runtime-3776AB?logo=python&logoColor=white](https://www.cloudcompare.org/)
https://img.shields.io/badge/CloudCompare-Python%20Plugin-00A896](https://www.cloudcompare.org/)
[![Documentation](https://img.shieldsation-Wiki-success?logo=github](https://github.com/adririquelme/DSEPy/wiki)

#features • #workflow • #installation • #documentation • #citation • #authors

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
* **[CloudCompare](https://www.cloudcompare.org/)** (v2.14.beta - build 2024-09-26 or higher required; earlier builds or older stable releases may cause Python binding issues).
* **CloudCompare Python Plugin** enabled during installation (ensure the Python plugin option is checked during the CloudCompare setup wizard).

---

#### 1. Download DSEpy
Clone or extract DSEpy into a simple directory path without spaces or special characters (e.g., `C:\CCPlugins\DSEPy`):
```bash
git clone https://github.com/adririquelme/DSEpy.git C:\CCPlugins\DSEPy
```

#### 2. Install Dependencies in CloudCompare's Python
Since CloudCompare is installed in `C:\Program Files\` by default, installing Python packages requires elevated administrator privileges.

1. **Close CloudCompare completely** if it is currently running.
2. **Open Command Prompt (CMD) or PowerShell as Administrator:**
   * Press `Win + S`, type `powershell` or `cmd`, right-click, and select **Run as administrator**.
3. **Navigate to the DSEpy directory:**
   ```cmd
   cd C:\CCPlugins\DSEPy
   ```
4. **Run the installation command:**

   * **In PowerShell:**
     ```powershell
     & "C:\Program Files\CloudCompare\plugins\Python\python.exe" -m pip install -r requirements.txt --no-warn-script-location --break-system-packages
     ```

   * **In Command Prompt (CMD):**
     ```cmd
     "C:\Program Files\CloudCompare\plugins\Python\python.exe" -m pip install -r requirements.txt --no-warn-script-location --break-system-packages
     ```

> 💡 **Troubleshooting & Notes:**
> * **Externally Managed Environment Error (PEP 668):** Newer CloudCompare 2.14.beta builds mark their embedded Python as externally managed. The `--break-system-packages` flag is required to allow `pip` to install packages directly into CloudCompare's Python environment.
> * **Permission Error / Access Denied (`WinError 5`):** Ensure your console was opened via **"Run as administrator"** and that **CloudCompare is completely closed**.
> * **PowerShell Syntax Error (`Unexpected token`):** In PowerShell, always include the `&` operator before quoted executable paths.
> * **NumPy 2.x Compatibility Issues:** CloudCompare plugins require **NumPy 1.x** (`numpy<2.0.0`). Ensure your `requirements.txt` restricts NumPy (`numpy>=1.20.0,<2.0.0`) to avoid C-extension errors (`ImportError: cannot import name '_c_internal_utils'`).

---

#### 3. Quick Start / Launching DSEpy
1. Open **CloudCompare**.
2. Open the **Python Console** (from the menu or toolbar).
3. Execute the launcher script:
   ```python
   exec(open("C:/CCPlugins/DSEPy/main_gui_v100.py").read())
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
