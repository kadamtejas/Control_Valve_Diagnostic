# Control Valve Diagnostics — v3.0

## What's new in v3

v3 wraps the existing v2 engine with four upstream modules. The v2 engine itself is untouched, so anything that worked before still works.

1. **Input Health Check** — 45+ checks covering file integrity, sheet structure, configuration sanity, data quality, and cross-consistency. Catches problems with the input file *before* the diagnostic runs and explains every finding in plain language.
2. **Missing-Data Repair** — sensibly fills tiny gaps, leaves bigger gaps alone, and skips loops with too much missing data. Never uses average-fill (which would create false frozen-sensor diagnoses).
3. **Outlier Handling** — removes physically impossible values (OP > 110%, negative absolute pressure, etc.) and isolated single-sample spikes. Keeps everything else, including step changes and sustained excursions, because those are usually real plant events.
4. **Auto-Calibration** — derives threshold values from your data, with five layers of safeguards. Falls back to manual values whenever it isn't confident. By default the tool runs in AUTO mode; pass `--manual` to use the values in your DIAGNOSTIC_CONFIG sheet exactly as written.

The four modules each produce their own report in plain text, sitting alongside the existing v2 outputs. Nothing is hidden — every repair, every removal, every threshold change is shown.

## How to run

For most users, see `QUICKSTART.md`. The summary:

```
python valve_diagnostics_v3.py --input my_data.xlsx --output-dir results
```

You need both `valve_diagnostics_v3.py` AND `valve_diagnostics_v2.py` in the same folder. v3 imports v2 as the engine.

## Command-line options

| Flag | What it does |
|------|--------------|
| `--input <file>` | Path to your Excel input. Required. |
| `--output-dir <dir>` | Where to write outputs. Default: `./diagnostics_output`. |
| `--manual` | Use your DIAGNOSTIC_CONFIG values exactly. Disables auto-calibration. Use this if you want v3 to behave identically to v2 on the diagnostics side. |
| `--skip-incomplete-loops` | Automatically skip loops that have more than 30% missing data, instead of blocking the run. |
| `--force` | Run even if the health check found problems. Not recommended — fix the issues first. |
| `--quiet` | Suppress console output. |

## What you get

Every run produces these files in the output directory:

| File | What's in it |
|------|--------------|
| `health_check_report.txt` | All 45+ checks: what passed, what didn't, how to fix |
| `data_repair_report.txt` | Every value the tool repaired, and why |
| `outlier_handling_report.txt` | Every value the tool removed or kept, and why |
| `auto_calibration_report.txt` | Each threshold: manual value, auto value, which was used, confidence level |
| `data_v3_processed.xlsx` | The cleaned, calibrated data the diagnostic actually ran on |
| `Loop_diagnostics_v2.xlsx` | The familiar Excel report from v2 |
| `Executive_summary.pdf` | The familiar PDF summary from v2 |
| `v3_run_summary.txt` | One-page overview of the run |
| `plots/` and dashboard PNGs | The familiar plot files from v2 |

## How AUTO calibration works

For each calibrated threshold, the tool:

1. **Layer 1 — Refusal.** Looks for "quiet" windows in each loop (regions where the signal sits still). A loop with no quiet window doesn't contribute to the baseline — it might already be a sick loop.
2. **Layer 2 — Peer comparison.** Groups loops by unit AND tag prefix (FIC together, TIC together, etc). Inside each group, drops anyone whose statistics are extreme outliers vs. their peers — those loops may be sick and shouldn't define what "normal" looks like.
3. **Layer 3 — Hard sanity bounds.** Each calibrated value is clamped within bounds set around the manual default (typically 0.5× to 3×). The tool can adapt to your data scale but cannot drift far enough to break diagnostics that were previously working. The `OP_ACTIVITY_THRESHOLD` is asymmetrically bounded — it can only rise above the manual default, never fall below it, because lowering it would hide real "unresponsive controller" cases.
4. **Layer 4 — Multi-method cross-check.** Even if one threshold is mis-calibrated, the four independent stiction methods (Heuristic, Horch, Yamashita, Bicoherence) plus Hägglund and Harris cross-check the diagnosis.
5. **Layer 5 — Confidence labels.** Each calibrated value is marked HIGH, MEDIUM, or LOW based on how much clean baseline data was available. Anything LOW falls back to the manual value automatically.

The auto-calibration report shows all of this for every parameter, every run.

## What stays MANUAL (never auto-calibrated)

These are industry-convention thresholds or physical limits — they don't depend on your specific data, so the tool leaves them at whatever you set in DIAGNOSTIC_CONFIG:

- `STICT_CONF_HIGH`, `STICT_CONF_MED`
- `PROP_CONF_MIN`, `PROP_CONF_STRONG`
- `SERVICE_FACTOR_MIN_PCT`
- `OSCILLATION_REGULARITY_MIN`
- `STICTION_S_MIN_PCT`
- `HARRIS_INDEX_THRESHOLD`
- `QUANTISATION_UNIQUE_VALS_MAX`, `COMPRESSION_FLAT_FRACTION_MAX`

## Mode column in DIAGNOSTIC_CONFIG

After v3 runs, your DIAGNOSTIC_CONFIG sheet (in `data_v3_processed.xlsx`) has four extra columns showing the full picture:

| Parameter | Value | Description | Manual_Value | Auto_Value | Mode_Used | Auto_Confidence |
|---|---|---|---|---|---|---|
| AMP_THRESHOLD | 7.5 | ... | 15 | 7.5 | AUTO | HIGH |
| OP_ACTIVITY_THRESHOLD | 1.5 | ... | 1.5 | 1.5 | AUTO | HIGH |
| ... | ... | ... | ... | ... | ... | ... |

Your original input file is never modified.

## Tested behaviour

- Synthetic dataset (8 loops, known faults): **8/8 correct** in both AUTO and MANUAL modes.
- Real plant data (10 loops): **MANUAL mode is 10/10 backward-compatible** with v2 (identical diagnoses). AUTO mode finds two additional candidate issues (sluggish tuning + confirmed stiction) due to more sensitive auto-calibrated thresholds — these are flagged for review, not asserted with high confidence.

## When AUTO mode might disagree with MANUAL mode

This is by design. AUTO calibrates the thresholds to your specific data, which can:
- Catch issues v2's defaults missed (because the defaults assumed % units across the board)
- Occasionally produce extra "Possible" calls on borderline loops

When AUTO finds something MANUAL didn't, treat it as a signal worth investigating — not a confirmed fault. The auto-calibration report shows the confidence level for every threshold so you know how much weight to give the result.

If you want the v3 wrapper benefits (input validation, repair reports, outlier reports) but the v2 diagnostic results, run with `--manual`.

## Honest limits

- v3 is a v1 of v3. It passes the regression tests on the synthetic and real-plant datasets that ship with this package. Real plants will surface things we'll need to fix; that's normal.
- Auto-calibration uses a single global threshold per parameter. A future v4 could go per-loop, but that requires changes to the v2 engine itself.
- Health check covers the most common failure modes seen in industrial Excel exports. There will be edge cases the checks don't anticipate.

When something goes wrong, the most useful files for diagnosis are `health_check_report.txt` (what the tool saw in your input) and `diagnostics.log` (what the v2 engine did with the cleaned data).

## Version

`valve_diagnostics v3.0.0` — wraps `valve_diagnostics_v2.py`. Both files must be present for v3 to run.
