# DSEPy Installation Guide

This guide describes the installation of DSEPy 1.0.0 for use with CloudCompare and its Python/`pycc` environment.

## 1. Prerequisites

You need:

- CloudCompare with a working Python/`pycc` environment.
- A compatible Python runtime available to CloudCompare.
- Internet access during the dependency-installation stage, unless the required Python wheels are already available locally.
- A Windows installation is recommended for DSEPy 1.0.0. Other platforms may require adaptation of the CloudCompare Python-runtime paths and have not been formally validated for this release.

DSEPy is not a standalone Python program: it imports `pycc` and communicates directly with the CloudCompare database.

## 2. Download DSEPy

From GitHub, either:

- select **Code → Download ZIP**, or
- clone the repository with Git.

The repository is:

`https://github.com/adririquelme/DSEpy`

For a reproducible first installation, use the `v1.0.0` release rather than the development branch.

## 3. Copy the DSEPy files

Keep the following structure together:

```text
DSEpy/
├── main_gui_v100.py
├── stereonet.py
├── colour_optimisation.py
├── i18n.py
├── icons/
└── locales/
```

The Python files, `icons` directory and `locales` directory must remain together. DSEPy resolves its plugin directory and loads these resources relative to the runtime/plugin location.

## 4. Install Python dependencies

The required packages are listed in `requirements.txt`:

```text
numpy
scipy
matplotlib
Pillow
colorcet
```

PyVista is optional and is only required for the interactive 3D normal/sphere visualisation.

### Important: install into the correct Python environment

Do **not** automatically install these packages into whichever Python installation happens to be first on your Windows PATH.

They must be available to the Python runtime used by CloudCompare/`pycc`.

DSEPy explicitly looks for user `site-packages` directories associated with the Python runtime version and adds required package/DLL directories to the import path. Therefore, installing packages into the wrong Python installation can result in errors such as:

```text
ModuleNotFoundError: No module named 'numpy'
```

or DLL-loading errors from NumPy/SciPy.

## 5. Verify the Python runtime

When DSEPy starts, it checks the embedded/runtime Python and reports dependency import errors with the Python version and executable path.

If an import error appears, first check that `numpy`, `scipy` and `matplotlib` are installed for that exact Python runtime.

## 6. Launch DSEPy

Run `main_gui_v100.py` using CloudCompare's Python environment/`pycc` mechanism.

The program title should report:

```text
DSE - Discontinuity Set Extractor 1.0.0
```

The GUI should then show the three workflow tabs:

1. **Principal poles**
2. **DS classification**
3. **Spatial clustering**

## 7. First test

A basic installation test is:

1. Start CloudCompare.
2. Load a point cloud.
3. Ensure the point cloud has valid normals.
4. Select the point cloud in CloudCompare.
5. Open DSEPy.
6. Press **Refresh**.
7. Confirm that the cloud status is detected and Step 1 becomes available.
8. Run **Calculate Density & Principal Poles**.
9. Confirm that the principal-pole table is populated.

If Step 1 succeeds, the core DSEPy/CloudCompare connection is working.

## 8. Persistent files

DSEPy may create local runtime files in its execution directory, including:

- `DSE_execution_log.txt` — execution and diagnostic log.
- `settings.json` — saved GUI/method settings.

These are deliberately excluded from Git by the repository `.gitignore` and should not normally be committed.

## 9. Recommended installation practice

For research use, keep separate copies of stable releases and development versions:

```text
DSEpy-v1.0.0/
DSEpy-development/
```

This avoids accidentally changing the version used to reproduce published results.

## 10. CloudCompare compatibility

CloudCompare's Python ecosystem is evolving. The DSEPy release should therefore be used with a CloudCompare Python/`pycc` environment that is known to work with the release.

If a future CloudCompare release changes its Python runtime, plugin directory structure or Python API, a new DSEPy release may be required.
