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
