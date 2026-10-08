# DSEpy - Installation Guide

This guide details the complete installation process for **DSEpy** within **CloudCompare**.

---

## 📋 Prerequisites

1. **CloudCompare** (v2.12 or higher recommended).
2. In the CloudCompare installer, enable the **Python Runtime** component. If it was omitted, rerun the installer in modify mode and add it. DSEpy must run in the Python environment provided by CloudCompare; a separate system Python is not a substitute.

---

## ⚠️ Crucial Concept: CloudCompare Python Runtime

DSEpy runs inside the Python environment used by CloudCompare. A bare `pip install ...` may target a different Python installation, so always invoke pip as `python.exe -m pip` using the Python Runtime's own interpreter.

---

## 📦 Step 1: Download DSEpy

Git is not required:

1. Open [DSEpy Releases](https://github.com/adririquelme/DSEpy/releases), choose the version you want, and download its **Source code (zip)** archive. To use the current development branch instead, select **Code → Download ZIP** on the repository page.
2. Extract the archive and keep the complete folder structure, including `icons` and `locales`, in a permanent location such as `C:\CCPlugins\DSEpy`.

Alternatively, if Git is installed:

```powershell
git clone https://github.com/adririquelme/DSEpy.git C:\CCPlugins\DSEpy
```

---

## 🛠️ Step 2: Install Dependencies in the CloudCompare Runtime

1. Open CloudCompare and its Python Console.
2. Run this code to inspect the Python version and executable used by the console:

   ```python
   import sys
   print(sys.version)
   print(sys.executable)
   ```

3. Close CloudCompare completely. Use the path to the Runtime's `python.exe`. If `sys.executable` returned that interpreter, use the printed path. If it returned `CloudCompare.exe` or another host executable, do not pass that host executable to pip; locate the `python.exe` installed with the CloudCompare Python Runtime. The location varies by CloudCompare version and installation folder.
4. In PowerShell, replace both example paths with the actual paths on your computer:

   ```powershell
   & "C:\Path\To\CloudCompare\PythonRuntime\python.exe" -m pip install --user -r "C:\CCPlugins\DSEpy\requirements.txt"
   ```

`-m pip` invokes pip for that exact interpreter. `--user` installs packages for the current Windows user and normally avoids writing to the protected `Program Files` directory. If pip is missing, verify that the Runtime component is installed and that you selected its `python.exe`; do not install dependencies into an unrelated system Python.

---

## ▶️ Step 3: Launch DSEpy

1. Open **CloudCompare** and load your 3D point cloud.
2. Open the **Python Console**.
3. Run the following code, replacing the example folder with the folder where you extracted or cloned DSEpy:

   ```python
   exec(open(r"C:\CCPlugins\DSEpy\main_gui.py", encoding="utf-8").read())
   ```

---

## 🔍 Verification and Logs

Upon launch, DSEpy generates an execution log named `DSE_execution_log.txt` in the working directory. 

If any module fails to load or if a dependency is missing, check `DSE_execution_log.txt` or refer to [`troubleshooting.md`](./troubleshooting.md).
