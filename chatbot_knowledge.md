# Control Valve Diagnostic Tool — Chatbot Knowledge Base
(Ingenero Technologies · POC · Ethylene fractionator plant, YN.ETH1 namespace, ~10 control loops)

## 1. What the tool is
A web application that reads DCS historian exports (Excel) and automatically diagnoses control loop / control valve health. It runs 8 diagnostic algorithms (stiction, oscillation, saturation, sluggish/aggressive tuning, unresponsive controller, signal noise, data quality, cross-loop propagation), scores each loop with a Health Index (0–100), and recommends concrete actions. The Tuning page identifies a process model (FOPDT/SOPDT) and computes IMC-PI controller settings (Kp, Ti) with simulated before/after improvement. Audience: plant operators, control engineers, plant managers. Runs locally at http://localhost:8001 (started by an engineer; not a 24/7 service). Each user logs in with email/password; results and configuration are per-user.

## 2. Pages
- **Dashboard** (main page): plant-wide health summary, heatmap, recommended actions, loop details, trends, configuration.
- **Tuning page**: opened via the "Tune Controller" button on a loop — controller retuning analysis (engineers).
- **Upload page**: upload a new plant data Excel file and run diagnostics; includes a DB configuration tab (tag format, loop management, thresholds) and a "How to Use" guide with downloadable user manual.
- **Config page**: per-user diagnostic selection and threshold configuration applied before each engine run.

## 3. Dashboard — Overview tab
**Top bar**: run badge shows which plant/run is loaded (e.g. YN.ETH1 · date) — confirms data currency.

**Four hero cards (summary tiles):**
1. **Plant Health** — large % = share of loops in good condition; loop status counts: Healthy / Watch / Critical, and total loops. Clicking opens the full loop status breakdown.
2. **Valve Problems** — % and counts for valve-related issues: Stiction, Valve Stuck, Saturation. These need *maintenance*, not retuning.
3. **Tuning Issues** — % and counts for controller tuning issues: Sluggishness, Sluggish Tuning, Aggressive Tuning, Unresponsive Controller. These are fixed by *retuning* (Tune Controller button).
4. **Operational & Signal** — % and counts for: Loop in Manual, Sensor Issue, Data Quality, External Oscillation (oscillation driven from another loop).

Clicking a hero card or a problem row inside it filters the Recommended Actions table to that group ("✕ Clear Filter" resets).

**Diagnostic Heatmap**: colour grid of all loops × diagnostic metrics for quick cross-loop comparison. Green = healthy, amber = watch, red = problem, grey = N/A. Filterable by unit and by loop (All Units / All Loops dropdowns).

**Recommended Actions table** — one row per detected issue:
| Column | Meaning |
|---|---|
| Issue | The problem type (e.g. Stiction, Sluggish Tuning) |
| Cause Parameter | The metric that triggered it (e.g. Stiction Conf., Hägglund Regularity, Harris Index) |
| Loop | The affected loop tag |
| Actual Value | Measured value of the cause parameter |
| Target / Threshold | The acceptable limit it violated |
| Recommended Action | What to do about it |

**Loop detail panel**: click any loop to open it. Shows loop tag with engineering unit (UOM), Health Score, diagnosis, and a trend chart of three DCS signals: **PV** (blue, measured process variable), **SP** (green dashed, setpoint/target), **OP** (orange, controller output / valve position 0–100%). Zoom by click-drag; ↺ resets; click legend items to toggle signals. Diagnostic evidence cards show stiction method scores, data quality details, and propagation (if an upstream loop is driving this loop's oscillation, shown with lag time and correlation). A **Tune Controller** button appears only for tuning-type diagnoses (sluggish/aggressive/unresponsive) — not for stiction/saturation, which need maintenance.

## 4. Dashboard — Technical Details tab
Full sortable metrics table, one row per loop (click headers to sort, click row for details):
| Column | Meaning | Good value |
|---|---|---|
| Health | Composite score 0–100 (IAE, Harris, service factor, severity penalty, data quality) | > 75 (50–75 = Watch/Poor, < 50 = Critical) |
| Severity | Critical / Poor / Good | Good |
| Diagnosis | Primary issue identified | Normal/Healthy |
| Stiction | Confirmed / Likely / Unlikely / No stiction | No stiction |
| Service % | Time in Auto/Cascade mode (low = often in Manual) | > 80% |
| IAE/hr | Integrated Absolute Error per hour — total SP tracking error | Lower is better |
| IAE norm% | IAE normalised to PV span — comparable across loops | Lower is better |
| Harris | Harris Index — minimum-variance benchmark; 1.0 = best achievable given dead time | Close to 1.0 |
| PV Amp | Peak-to-peak PV variation | Low, stable |
| OP Act | Std-dev of controller output — valve movement (wear indicator) | Low |
| Hägglund | Oscillation regularity index | < 0.60 |
| Dom. Period | Dominant oscillation period (from error ACF) | — |
| Conf % | Confidence of the diagnosis | Higher = more reliable |
| Data Quality | Pass / Warn / Fail (missing, frozen, out-of-range samples) | Pass |

## 5. Dashboard — Monitoring tab
- **Loop Trends**: PV/SP/OP trend charts per loop, with reset axes and expand buttons.
- **Tag Explorer**: plot any raw historian tags; group by None / Unit / Loop / Type; time range presets 15 min / 1 hr / 8 hr / 24 hr / 7 days / All; multi-select tags then Apply; Clear all resets.

## 6. Dashboard — Configuration Settings
(Engineer use; changes apply on the next diagnostic run.) Sub-tabs:
- **Parameters**: threshold values per diagnostic (parameter, value, description).
- **Detection Methods**: enable/disable individual algorithms (stiction methods, oscillation, saturation, sluggish/aggressive, noise, data quality).
- **Required Diagnostics**: choose which diagnostics must run.
- **Mode Mapping**: map controller mode values (Auto/Manual/Cascade) from the plant's data conventions.
- **Unit Mapping**: map loops/tags to plant units/sections, and engineering units (UOM).
Per-user configuration is saved per login and written into the input workbook before the engine runs.

## 7. Diagnoses — what each means
| Diagnosis | Meaning | Typical cause | Fix path |
|---|---|---|---|
| Stiction | Valve sticks then jumps — OP changes don't smoothly move PV; causes limit cycling | Packing wear, corrosion | Maintenance (not retuning) |
| Valve Stuck | Valve not responding to OP at all | Mechanical failure | Maintenance |
| Saturation | OP pinned at 0% or 100% for sustained periods | Undersized valve, process upset | Maintenance / process review |
| Oscillation | PV cycles regularly around SP | Aggressive tuning or stiction | Identify source, then retune or maintain |
| External Oscillation | Oscillation imported from an upstream loop (propagation) | Disturbance from another loop | Fix the source loop first |
| Sluggish Tuning / Sluggishness | Slow SP tracking, high IAE — tuning too conservative | Kp too low / Ti too long | Retune (increase gain) |
| Aggressive Tuning | Fast but oscillatory response | Kp too high | Retune (reduce gain) |
| Unresponsive Controller | Controller barely acting (low OP activity, poor Harris) | Severely detuned or in wrong mode | Retune / check mode |
| Loop in Manual | Low service factor — loop frequently not in Auto/Cascade | Operator practice, distrust of loop | Investigate why operators bypass it |
| Sensor Issue | Frozen/implausible PV readings | Sensor or wiring fault | Instrument maintenance |
| Signal Noise | High-frequency noise on PV masking true behaviour | Sensor, wiring, process | Filtering / instrumentation |
| Data Quality | Insufficient/invalid data for reliable diagnosis | Missing data, frozen values | Fix historian export / sensor |

**Stiction detection — 4-method consensus** (Confirmed when ≥ 2 methods agree):
Heuristic (PV oscillates while OP static), Horch cross-correlation (lag asymmetry), Yamashita (OP-PV phase plot shape), Bicoherence (harmonic distortion from nonlinearity).

## 8. Tuning page (engineers)
Open via Tune Controller on a sluggish/aggressive/unresponsive loop. Layout: Parameter Comparison + Expected Outcomes (row 1), Actual vs Optimised chart (row 2), Hold-out Cross-Validation + Process Model & Parameters collapsible cards (row 3), Action Plan + Engineer Notes / Accept & Save (row 4). A config drawer exposes tuning parameters.

**Parameter Comparison**: Current (Estimated) vs Recommended for Kp (proportional gain — higher = faster but more oscillatory), Ti (integral time, min — smaller = faster reset), λ (IMC speed target — larger = slower/more robust; λ = max(2θ, 0.6·Tu, 0.5·τ, λ_floor)). Change column shows direction, % change, and a one-line reason. **Important**: "Current (Estimated)" values are reverse-engineered from closed-loop data, not read from the DCS — always verify against the actual DCS configuration before applying.

**Expected Outcomes**: BEFORE (real recorded data) vs Auto Optimised (AO, simulated with recommended Kp/Ti) vs User Optimised (UO, simulated with user-entered Kp/Ti). Metrics: IAE total (lower better; 20–40% reduction is excellent), OP Activity σ (lower = less valve wear/longer valve life), PV Noise σ (a plant/sensor property — tuning cannot improve it). A small IAE gain can still be worth applying if OP activity reduction is large (valve wear savings).

**Actual vs Optimised chart**: overlays SP (green dashed), PV Current (dark navy), PV Optimised (sky blue), OP Current (orange), OP Optimised (amber). Good result = blue PV Optimised hugs SP closer than dark PV Current, and amber OP smoother than orange. Toggle via legend; zoom by drag; ↺ resets; Current / Auto Optimised buttons switch overlay.

**Process Model & Parameters** (collapsible): model badge FOPDT (blue, monotonic first-order response — most flow/pressure/temperature loops), SOPDT (purple, S-shaped response with inflection — two dominant lags), or Integrating (amber, level loops — FOPDT doesn't apply). A reason box explains the selection. Parameters with confidence bars (High/Medium/Low):
- **K** process gain — steady-state ΔPV per 1% ΔOP (typ. 0.1–5). Estimated from median ΔPV/ΔOP across detected OP steps (|ΔOP| ≥ 3%, low pre-step variance); windowed OLS fallback when no clean steps. PV normalised to 0–100% span first.
- **θ** dead time — delay before PV responds (typ. 0.5–10 min), from OP↔PV cross-correlation peak.
- **τ₁** primary time constant — time to 63.2% of final value (typ. 1–60 min); fallbacks: ACF decay (fast loops), variance ratio.
- **τ₂** (SOPDT only) — second lag from Broida 2-point method (t₁ at 28.3%, t₂ at 63.2% of ΔPV; τ_eff = 5.5·(t₂−t₁), τ₂ = 0.33·τ_eff).
- **Tu** oscillation period from error ACF (typ. 3–25 min).
SOPDT is selected when ≥ 50% of valid steps show an inflection point. Low confidence ⇒ estimate may be unreliable ⇒ run a dedicated open-loop step test (AUTO, ΔOP ≥ 5%) before applying.

**Tuning formulas**: FOPDT IMC-PI: Kp = τ/(K·(λ+θ)), Ti = clamp(τ, 0.5τ, 4(λ+θ)). SOPDT: Kp = (τ₁+τ₂)/(K·(λ+θ)), Ti = τ₁+τ₂. Level (integrating): Kp = 1/(Ki·λ²), Ti = 2λ, with Ki from dPV/dt vs OP deviation. When K confidence is Low, the recommendation is anchored to the existing Kp with a direction multiplier rather than trusting the raw formula.

**Hold-out Cross-Validation** (collapsible): data split 70/30 train/validate; K estimated on each half; table compares K_original / K_train / K_validate. Large train-vs-validate difference = non-stationary gain → apply tuning with caution.

**Action Plan**: exact Kp and Ti values to enter in the DCS, expected PV σ to monitor for 2–4 hours after the change, K-confidence note, and loop-type warnings (temperature loops always: run a step test first — thermal time constants vary too much for historian data alone).

**User Optimised override**: enter custom Kp/Ti → Apply User Tuning → UO column and chart update. Simulation only — values are never written to the DCS.

**Accept & Save**: optional Engineer Notes, then Accept & Save Recommendation → green ✓ Saved with timestamp; the loop shows a Tuned badge on the dashboard. Saved recommendations are in-memory — lost on server restart, so note values or export before restarting.

**Engineer workflow**: open loop → check loop-type badge (avoid applying FOPDT results to Level/Unknown) → review model badge + reason → check K confidence → review Parameter Comparison → review Expected Outcomes (>15% improvement is meaningful) → verify chart → optionally test custom Kp/Ti → run hold-out validation → add notes → Accept & Save → enter values in DCS → monitor PV σ for 2–4 h.

## 9. Loop types
| Type | τ range | Model | Notes |
|---|---|---|---|
| Flow (FC) | 0.5–20 min | FOPDT/SOPDT | Fast; τ capped at 20 min; usually high confidence |
| Pressure (PC) | 0.5–30 min | FOPDT/SOPDT | Can be integrating in gas headers; verify if confidence Low |
| Temperature (TC) | 5–120 min | FOPDT/SOPDT | τ floor 5 min; slow — step test strongly recommended |
| Level (LC) | Integrating | Integrating | FOPDT does not apply; special formulas used |
| Unknown | unbounded | FOPDT default | Tag didn't match naming convention; review carefully |
Tag convention: instrument code between digit groups, e.g. 15FC317, 22TC101. Excel files need a loop_format sheet (else default _PV/_OP/_SP suffixes are assumed).

## 10. Upload & data
Upload page: drag-and-drop the DCS historian Excel export, then run diagnostics. The workbook contains the time-series sheet plus DIAGNOSTIC_CONFIG, DIAGNOSTIC_SELECTION, UNIT_MAPPING and MODE_MAPPING sheets. The DB configuration tab lets you define the tag format, manage loops, and review thresholds. A "How to Use" guide and downloadable user manual are available on this page.

## 11. Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| "Server timed out — is uvicorn running on port 8001?" | Backend not running | Ask the engineer to start the server |
| 404 on tune page | No diagnostic run loaded | Run a diagnostic from the dashboard first |
| Loop type "unknown" | Tag doesn't match naming pattern | Check tag convention (FC/PC/TC/LC between digit groups) |
| τ confidence Low | No clean OP steps (loop in manual / little movement) | Run a step test in AUTO with ΔOP ≥ 5% |
| "FOPDT model not valid" on level loop | Level loops are integrating | Use the integrating-process tuning shown; don't apply FOPDT Kp/Ti |
| Tuning recommendation lost | Server restarted (in-memory storage) | Note values before restart |
| Small predicted improvement | Tuning already near-optimal or low K confidence | Check confidence; consider a step test |

## 12. Glossary
**PV** measured process variable · **SP** setpoint (target) · **OP** controller output to valve (0–100%) · **DCS** Distributed Control System · **IAE** Integrated Absolute Error ∫|PV−SP|dt, lower is better · **Harris Index** minimum-variance benchmark, 1.0 = theoretical optimum · **Service Factor** % time in Auto/Cascade · **Stiction** static valve friction causing stick-jump motion and limit cycles · **FOPDT/SOPDT** First/Second Order Plus Dead Time process models · **K** process gain · **θ** dead time · **τ** time constant · **Tu** oscillation period from error ACF · **λ** IMC closed-loop speed target (larger = slower/safer) · **Kp** proportional gain · **Ti** integral time (min) · **ACF** autocorrelation function · **Hägglund index** oscillation regularity measure · **IMC-PI** Internal Model Control PI tuning method · **UOM** unit of measure shown next to a loop's PV.

## 13. Known limits (POC)
- Local app, not hosted 24/7; login required; results isolated per user.
- "Current (Estimated)" Kp/Ti are indicative, reverse-engineered — verify in DCS.
- Saved tuning recommendations are in-memory only (lost on restart).
- PDF/report export is planned for a future phase.
- Works with any plant's Excel export if the loop_format/tag conventions are followed — not limited to the ethylene fractionator.
