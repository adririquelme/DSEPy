# DSEpy - Installation Guide

This guide details the complete installation process for **DSEpy** within **CloudCompare**.

---

## 📋 Prerequisites

1. **CloudCompare** (v2.12 or higher recommended).
2. **CloudCompare Python Plugin** enabled (e.g., CloudComPy or standard Python wrapper).

---

## ⚠️ Crucial Concept: CloudCompare Embedded Python

DSEpy runs inside CloudCompare's embedded Python interpreter. Installing packages using standard Windows command prompt (`pip install ...`) will install dependencies into system Python, **not into CloudCompare's Python environment**.

To ensure DSEpy works properly, packages must be installed directly into CloudCompare's Python distribution.

---

## 🛠️ Step-by-Step Installation

### Step 1: Identify CloudCompare's Python Executable

1. Open **CloudCompare**.
2. Open the **Python Console** / plugin panel.
3. Run the following code to retrieve the exact path of the Python executable used by CloudCompare:

```python
import sys
print("CloudCompare Python Executable:")
print(sys.executable)
```

Example output:
`C:\Program Files\CloudCompare\python\python.exe`

---

### Step 2: Install Required Dependencies

You can install dependencies using either of two methods:

#### Method A: Via Windows Terminal (PowerShell / CMD) — *Recommended*
Open Windows Command Prompt or PowerShell and run `pip` using the exact executable path obtained in Step 1:

```cmd
"C:\Program Files\CloudCompare\python\python.exe" -m pip install numpy scipy matplotlib Pillow
```

*To install optional packages for enhanced 3D rendering and color maps:*
```cmd
"C:\Program Files\CloudCompare\python\python.exe" -m pip install colorcet pyvista
```

#### Method B: Directly Inside CloudCompare Python Console
Paste and execute this snippet inside CloudCompare's Python console:

```python
import subprocess
import sys

required_packages = ["numpy", "scipy", "matplotlib", "Pillow"]

print("Installing DSEpy dependencies...")
subprocess.check_call([sys.executable, "-m", "pip", "install"] + required_packages)
print("Installation complete!")
```

---

### Step 3: Set Up DSEpy Directory Structure

1. Download the latest release from the [GitHub Releases page](https://github.com/adririquelme/DSEpy/releases) or clone the repository:
   ```bash
   git clone [https://github.com/adririquelme/DSEpy.git](https://github.com/adririquelme/DSEpy.git)
   ```
2. Ensure the relative paths are preserved in your local installation directory:

```text
DSEpy/
├── main_gui_v100.py
├── colour_optimisation.py
├── stereonet.py
├── i18n.py
├── icons/
│   ├── add.png
│   ├── apply.png
│   └── ...
├── locales/
│   ├── en.json
│   ├── es.json
│   └── ...
└── docs/
```

---

### Step 4: Launching DSEpy

1. Open **CloudCompare** and load your 3D point cloud (with computed normal vectors).
2. Open the **Python Console**.
3. Launch the main script:

```python
import os
script_path = r"C:\Path\To\DSEpy\main_gui_v100.py"
exec(open(script_path, encoding='utf-8').read())
```

---

## 🔍 Verification and Logs

Upon launch, DSEpy generates an execution log named `DSE_execution_log.txt` in the working directory. 

If any module fails to load or if a dependency is missing, check `DSE_execution_log.txt` or refer to [`troubleshooting.md`](./troubleshooting.md).
