# Quick Start — Valve Diagnostics v3

This is the 5-minute guide. The longer reference is in `README_v3.md`.

## Step 1 — Install Python (one time only)

If you've never run Python on this computer:

**Windows:**
1. Go to https://www.python.org/downloads/
2. Download the latest Python 3 installer.
3. **Important:** when running the installer, tick the box that says *"Add Python to PATH"* before clicking Install.
4. Restart your computer once after installation.

**Mac:**
1. Open Terminal (press Cmd+Space, type Terminal, press Enter).
2. Type `python3 --version` and press Enter. If it shows a version number ≥ 3.9, you're done.
3. Otherwise, install from https://www.python.org/downloads/.

You only do this once, ever, on each computer. Skip this step if Python is already installed.

## Step 2 — Install the libraries the tool needs (one time only)

In the folder where you unzipped this package:

**Windows:** double-click `INSTALL.bat`.

**Mac/Linux:** open Terminal in this folder and run:
```
bash install.sh
```

You'll see a stream of "installing" messages for about a minute. When it ends with "Installation complete," you're done. You only do this once.

## Step 3 — Run the tool

You have three ways to run it. Pick whichever you like.

### Easiest: drag-and-drop (Windows only)

Drag your Excel data file onto `RUN_AUTO.bat`. A console window opens, the tool runs, and the results appear in a folder called `results_<your_filename>` next to the .bat file.

To use manual thresholds (your existing DIAGNOSTIC_CONFIG values, no auto-calibration), drop the file onto `RUN_MANUAL.bat` instead.

### Try the test data first

Double-click `RUN_TEST_SYNTHETIC.bat` to run the tool against the bundled synthetic dataset. This is the safest way to confirm everything is installed correctly. After the run finishes, open the `results_synthetic_test_data` folder and look at `Loop_diagnostics_v2.xlsx` — you should see 8 loops with the diagnoses listed in the README.

`RUN_TEST_REAL_PLANT.bat` does the same with the bundled real-plant export.

### Command line (any platform)

```
python valve_diagnostics_v3.py --input my_data.xlsx --output-dir results
```

Add `--manual` to disable auto-calibration. Add `--skip-incomplete-loops` to skip loops with too much missing data instead of being blocked.

## Step 4 — Read the results

In the output folder, the most useful files (in order):

1. **`v3_run_summary.txt`** — one-page overview of the whole run.
2. **`health_check_report.txt`** — every input check, what passed, what didn't.
3. **`Loop_diagnostics_v2.xlsx`** — the familiar Excel report (Summary sheet first).
4. **`Executive_summary.pdf`** — the PDF version.
5. **`auto_calibration_report.txt`** — every threshold value, manual vs. auto, with confidence labels.
6. **`data_repair_report.txt`** — every value the tool repaired, and why.
7. **`outlier_handling_report.txt`** — every value the tool removed, and why.
8. **`data_v3_processed.xlsx`** — the cleaned data the diagnostic actually ran on. Useful if you want to inspect what the tool was looking at.

Your original input file is **never modified.**

## When something goes wrong

If the run stops with a "PROBLEM" — the health check caught something that would have produced a wrong answer. The error message tells you exactly what to fix.

If the run finishes but a result looks wrong — the most useful thing to share with whoever supports this tool is:
- The input file
- The full output folder (zip it)

Those two together let anyone reproduce the run and see what the tool was thinking.

## What's in this package

```
valve_diagnostics_v3/
├── README_v3.md                    Full reference
├── QUICKSTART.md                   This file
├── valve_diagnostics_v3.py         The wrapper (the new thing)
├── valve_diagnostics_v2.py         The diagnostic engine
├── requirements.txt                Python libraries the tool needs
├── INSTALL.bat                     Windows: one-click installer
├── install.sh                      Mac/Linux: one-click installer
├── RUN_AUTO.bat                    Windows: drag-and-drop in AUTO mode
├── RUN_MANUAL.bat                  Windows: drag-and-drop in MANUAL mode
├── RUN_TEST_SYNTHETIC.bat          Windows: run on synthetic test data
├── RUN_TEST_REAL_PLANT.bat         Windows: run on real plant test data
├── run.sh                          Mac/Linux: run on a file you specify
├── test_data/
│   ├── synthetic_test_data.xlsx    8 loops with known faults — for testing
│   └── My_plant_data_1.xlsx        10 loops from a real ethanol plant
└── example_output/
    └── (results from running on synthetic_test_data.xlsx)
```

The example output folder shows you what a known-good run looks like before you run anything yourself.
