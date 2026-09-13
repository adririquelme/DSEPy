# DSEPy Troubleshooting Guide

## DSEPy does not start

Check that:

1. CloudCompare is running with a working Python/`pycc` environment.
2. `main_gui_v100.py`, `stereonet.py`, `colour_optimisation.py` and `i18n.py` are together.
3. The `icons` and `locales` directories are present.
4. Required Python packages are installed in the Python runtime used by CloudCompare.

## `ModuleNotFoundError: No module named 'pycc'`

This indicates that DSEPy is not being executed by the CloudCompare Python environment.

Do not try to solve this by installing a random `pycc` package with `pip`. Use the Python runtime/plugin mechanism provided by the CloudCompare installation.

## `ModuleNotFoundError` for NumPy/SciPy/Matplotlib/Pillow

Check which Python executable CloudCompare is using. DSEPy reports the runtime executable when dependency import fails.

Install the missing package into that environment rather than another system Python installation.

## NumPy/SciPy DLL errors on Windows

Binary Python packages must be compatible with the Python version and architecture used by CloudCompare.

DSEPy registers common package DLL directories when possible, but this cannot compensate for incompatible wheels.

## DSEPy cannot find its plugin directory

DSEPy searches several locations, including the directory containing the script, common Windows CloudCompare/plugin locations and Python paths.

Make sure `stereonet.py` is in the same DSEPy directory as `main_gui_v100.py`.

## No point cloud is detected

1. Load a point cloud into CloudCompare.
2. Select it in the DB tree.
3. Ensure it contains computed normals.
4. Press **Refresh** in DSEPy.

## Step 1 remains unavailable

The selected entity must be a valid point cloud with accessible normals. Refresh after changing the selected CloudCompare entity.

## Principal poles are not detected

Check:

- density/bin resolution;
- bandwidth;
- minimum separation angle;
- maximum number of poles;
- the quality and orientation consistency of the input normals.

Remember that the automatically detected poles are candidates and should be reviewed before DS classification.

## Step 2 is unavailable

Step 2 requires valid principal poles from Step 1. Complete and review the principal-pole calculation first.

## Step 3 is unavailable

Step 3 requires the DS classification field. Run Stage 2 first and refresh the workflow if necessary.

## Normal Colour Optimisation is unavailable

The Tools command is enabled only when the selected CloudCompare data provide the information required by the optimisation.

Check the selected cloud, its normals and the current workflow state.

## A language does not appear correctly

Check that:

- the corresponding JSON file exists in `locales/`;
- the file is valid UTF-8;
- its message-key structure matches `en.json`.

DSEPy keeps `en.json` as the reference message structure.

## Translations appear mixed with English

The GUI is translated through the i18n manager and the locale JSON files. If a string remains in English, identify the exact message key and check whether the corresponding locale contains a translated value.

For bug reports, attach the DSE execution log and specify the selected language.

## Where is the execution log?

DSEPy writes:

```text
DSE_execution_log.txt
```

in the DSEPy/plugin directory. The log records the same translated messages shown by the GUI and is useful for diagnosing calculation, CloudCompare and internationalisation problems.

## Settings are behaving unexpectedly

DSEPy stores GUI/method settings locally. If a stale setting is suspected, close DSEPy and inspect/remove the local `settings.json` file, then restart and reconfigure the method.

## Cluster facets cannot be created

Check that:

- Stage 3 has completed;
- `Discontinuity Set (DS)` exists;
- `Cluster id (cl)` exists;
- clusters contain enough valid points;
- fitted normals and coordinates are finite;
- the selected facet shape is valid.

The facet-generation routine validates individual clusters and reports failures without intentionally discarding valid clusters from the remainder of the operation.
