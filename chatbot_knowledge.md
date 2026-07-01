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

### When a loop is NOT tunable (recommended action is not the same as valid Kp/Ti)
A loop having a "recommended action" does NOT mean the tool can produce valid tuning numbers (Kp/Ti). These are two different things:
- The diagnosis may suggest a generic action (e.g. "increase gain / shorten Ti" for sluggish tuning).
- But the tuning engine can only deliver real Kp/Ti values when its model parameters were successfully estimated from the data.

A loop is effectively NOT auto-tunable from the historian data when any of these appear on the Tuning page — in which case the loop needs a dedicated open-loop step test (AUTO, ΔOP ≥ 5%) BEFORE any values can be applied:
- "Ki could not be estimated — insufficient OP excitation" on a Level (LC) loop. Level loops are integrating; without Ki, the integrating formula cannot produce valid Kp/Ti, so the loop is NOT tunable from this data even though a generic sluggish action may be listed.
- τ or K confidence is Low, or the page says "run a step test" (common for Temperature / TC loops and any loop with little OP movement).
- Expected-improvement / outcome figures show "not available" or "not applicable".

Rule for answering: do NOT tell the user a loop is tunable just because a recommended action exists. If Ki is missing or a step test is required, say the loop is not tunable from the current data and a step test is needed first.

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
| "Ki could not be estimated" / LC loop shows no Kp,Ti | Insufficient OP excitation in historian data | Loop is NOT tunable from this data; run an open-loop step test (AUTO, ΔOP ≥ 5%) first |
| Tuning recommendation lost | Server restarted (in-memory storage) | Note values before restart |
| Small predicted improvement | Tuning already near-optimal or low K confidence | Check confidence; consider a step test |

## 12. Glossary
**PV** measured process variable · **SP** setpoint (target) · **OP** controller output to valve (0–100%) · **DCS** Distributed Control System · **IAE** Integrated Absolute Error ∫|PV−SP|dt, lower is better · **Harris Index** minimum-variance benchmark, 1.0 = theoretical optimum · **Service Factor** % time in Auto/Cascade · **Stiction** static valve friction causing stick-jump motion and limit cycles · **FOPDT/SOPDT** First/Second Order Plus Dead Time process models · **K** process gain · **θ** dead time · **τ** time constant · **Tu** oscillation period from error ACF · **λ** IMC closed-loop speed target (larger = slower/safer) · **Kp** proportional gain · **Ti** integral time (min) · **ACF** autocorrelation function · **Hägglund index** oscillation regularity measure · **IMC-PI** Internal Model Control PI tuning method · **UOM** unit of measure shown next to a loop's PV.

**Diagnostic Heatmap column labels** (short labels shown in the Overview heatmap grid): **Reg** = Hägglund oscillation regularity index (≥0.60 flags sustained oscillation, ≥0.75 external) · **IAEnorm** = IAE norm% (IAE normalised to PV span, comparable across loops) · **OPact** = OP Activity (std-dev of controller output; valve-wear indicator) · **PVamp** = PV Amplitude (peak-to-peak PV variation) · **Conf** = Confidence % of the diagnosis · **dataQ** = Data Quality (Pass / Warn / Fail).

## 13. Known limits (POC)
- Local app, not hosted 24/7; login required; results isolated per user.
- "Current (Estimated)" Kp/Ti are indicative, reverse-engineered — verify in DCS.
- Saved tuning recommendations are in-memory only (lost on restart).
- PDF/report export is planned for a future phase.
- Works with any plant's Excel export if the loop_format/tag conventions are followed — not limited to the ethylene fractionator.

## 14. Formulas and Term Calculations

This section documents the exact formulas used inside the tool engine. Use this to explain how any metric is calculated or why a diagnosis was triggered.

### IAE (Integrated Absolute Error) (heatmap label: IAEnorm)
IAE_total = sum(|PV - SP|) over all samples
IAE/hr = IAE_total / duration_in_hours
IAE/hr normalised (%) = (IAE/hr / PV_scale) x 100
  where PV_scale = max(|mean(PV)|, 4 x std(PV), 1.0)
This normalisation makes IAE comparable across loops with different engineering units and scales.
Default threshold: IAE/hr > 200 OR IAE_norm% > 15% flags poor tracking.

### OP Activity (heatmap label: OPact)
OP Activity = mean(|OP[i] - OP[i-1]|) over all samples — the average absolute step in controller output per sample.
Default threshold: > 1.5 flags high valve movement / potential stiction or aggressive tuning.

### PV Amplitude (heatmap label: PVamp)
PV Amplitude = max(PV) - min(PV) — peak-to-peak range of the process variable.
PV Amplitude % = (PV Amplitude / PV_scale) x 100 — relative to the operating scale.
Used in stiction heuristic and oscillation detection (>5% of scale flags significant oscillation).

### Service Factor
Service Factor (%) = (number of samples in AUTO or CASCADE mode / total samples) x 100.
Default threshold: < 70% triggers "Loop in Manual" diagnosis.

### Harris Index (Minimum Variance Benchmark)
Based on Harris (1989). Measures how close a loop is to the theoretical minimum variance achievable given its dead time.
Formula:
  1. Compute error e[t] = PV[t] - SP[t]
  2. Fit an AR(p) model to e using Yule-Walker equations (p = max(AR order, dead_time + 5), capped at N/4)
  3. Compute AR residual variance: sigma_e^2 = r[0] - phi . r[1:p]
  4. Compute impulse response h[0..b] of 1/A(q) where b = dead time in samples
  5. sigma_mv^2 = sigma_e^2 x sum(h[0..b-1]^2) — minimum achievable variance
  6. Harris Index = sigma_mv^2 / var(e) — clipped to [0, 1]
Interpretation: 1.0 = ideal (already at minimum variance). 0.0 = no control benefit.
Dead time (b) is estimated from the peak lag in the OP to PV cross-correlation.
Default threshold: Harris < 0.3 is considered poor. NaN is returned when OP is near-static (treated as passing the gate, not failing).

### Hagglund Oscillation Regularity (heatmap label: Reg)
Measures how regular (periodic) the oscillations are, based on zero-crossing spacing of the error signal.
Formula:
  1. Compute error e[t] = PV[t] - SP[t], apply mild 5-sample rolling mean low-pass filter
  2. Find all zero-crossing indices of e
  3. Compute intervals between consecutive zero crossings
  4. Regularity = 1 / (1 + std(intervals) / mean(intervals))
  5. Dominant period (samples) = 2 x mean(intervals)
Regularity is in [0, 1]. 1.0 = perfectly periodic. 0.0 = random.
Thresholds: >= 0.6 triggers oscillation flag (aggressive tuning gate); >= 0.75 used for external oscillation gate (stricter, since downstream attenuation reduces regularity).

### Stiction Detection — 4 Methods
All scores are 0-100. Final consensus is a weighted average.

Method 1 — Heuristic (weight 0.25)
Uses a sigmoid-like soft function: soft(x, thr) = 100 x (x/thr) / (x/thr + 1), so x = threshold gives score ~50, x = 3x threshold gives ~85.
score = 0.40 x soft(OP_activity, OP_ACTIVITY_THRESHOLD)
      + 0.25 x soft(PV_amplitude, AMP_THRESHOLD)
      + 0.20 x soft(IAE/hr, IAE_PER_HOUR_THRESHOLD)
      + 0.15 x soft(OP_reversals_per_sample, 0.1)
where OP_reversals = number of sign changes in diff(OP).

Method 2 — Horch Cross-Correlation (weight 0.30)
Based on Horch (1999). Under no stiction, the cross-correlation r_{OP,PV}(lag) is even-symmetric. Under stiction it becomes asymmetric.
Decompose r_{OP,PV} into even and odd parts.
score = min(energy_odd / (energy_total x 0.5), 1.0) x 100
Higher score = more asymmetry = more stiction-like.

Method 3 — Yamashita Shape Classifier (weight 0.25)
Examines the PV-vs-OP phase plot shape (range-normalised to [0,1]):
- Straight/tight line: healthy (score 0)
- Ellipse (smooth corners): backlash/hysteresis (score ~45)
- Parallelogram (sharp corners, closed area): stiction (score 60-95)
Sharp corners detected by angle between incoming/outgoing path vectors at each OP reversal. cos(angle) < -0.5 = sharp corner.
score = 60 + 35 x (sharp_fraction) for parallelogram shape.

Method 4 — Bicoherence (weight 0.20)
Detects frequency-domain nonlinearity. Stiction creates harmonics which produce elevated bicoherence.
b^2(f1, f2) = |E[X(f1).X(f2).X*(f1+f2)]|^2 / (E[|X(f1).X(f2)|^2] . E[|X(f1+f2)|^2])
score = min(mean_bicoh / 0.5, 1.0) x 50 + min(sig_fraction / 0.15, 1.0) x 30
where sig_fraction = fraction of frequency bins with bicoherence above noise threshold (6 / n_segments).

Consensus Combination
consensus_score = 0.25 x heuristic + 0.30 x horch + 0.25 x yamashita + 0.20 x bicoherence
(weights re-normalised if any method is disabled)
methods_agreeing = count of enabled methods with individual score > 50.
Labels:
  consensus >= STICT_CONF_HIGH (default 70) AND methods_agreeing >= 2: Confirmed
  consensus >= 70 but fewer than 2 agreeing: Likely
  consensus >= STICT_CONF_MED (default 40): Possible
  else: Healthy

Rossi-Scali S and J estimation
S (stickband, % OP) = median OP excursion before PV starts moving after each OP reversal.
J (slip-jump, % OP) = median PV jump at first-move point, mapped back to OP units via local gain.

### Diagnosis Gate Conditions (exact engine logic, priority order)

Diagnoses are checked in strict priority order — first match wins. Lower priority diagnoses are never checked once a higher one fires.

Priority 1 — Sensor / Frozen PV:
  PV standard deviation < 0.01 (near-zero variation = frozen signal)

Priority 2 — Data Quality (compression):
  More than 30% of consecutive PV samples are identical (historian compression artefact)

Priority 3 — Loop in Manual:
  Service factor < SERVICE_FACTOR_MIN_PCT (default 70%)

Priority 4 — Saturation:
  OP >= 98% OR OP <= 2% for more than 20% of samples

Priority 5 — Stiction:
  consensus_score >= STICT_CONF_HIGH (default 70) AND methods_agreeing >= 2
  OR consensus_score >= STICT_CONF_MED (default 40) with supporting evidence
  (stiction is checked before oscillation — a sticking valve causes oscillation but the root cause is mechanical)

Priority 6a — Aggressive Tuning:
  ALL of these must be true:
  1. Hägglund regularity >= osc_min (default 0.6) — sustained periodic oscillation
  2. PV amplitude > 5% of PV operating value OR absolute PV amplitude > 5.0 — oscillation is significant
  3. OP activity > OP_ACTIVITY_THRESHOLD (default 1.5)
     OR (regularity >= 0.85 AND OP activity > 0.5 x threshold) — softer gate for near-perfect limit cycles
  4. Harris Index < HARRIS_INDEX_THRESHOLD (default 0.3) — poor control performance
  Note: OP activity IS a gate condition here. The logic is: if OP is moving in step with PV, the controller is the cause of the oscillation (aggressive tuning). If OP is NOT moving much but PV is still oscillating, the cause is external (see below).

Priority 6b — External Oscillation:
  ALL of these must be true:
  1. Hägglund regularity >= 0.75 (stricter than aggressive tuning — downstream attenuation reduces regularity)
  2. PV amplitude significant (same as above)
  3. OP activity < 0.3 x OP_ACTIVITY_THRESHOLD — OP is near-static (controller NOT fighting)
  4. Harris Index < threshold OR NaN (NaN is expected when OP is near-static)

Priority 7 — Sluggish Tuning:
  Harris Index < threshold AND no oscillation detected AND OP activity low

Priority 8 — Healthy:
  None of the above fired

Key distinction — Aggressive vs External oscillation:
  Aggressive tuning: PV oscillates AND OP oscillates with it (controller is causing it)
  External oscillation: PV oscillates BUT OP is near-static (disturbance coming from upstream, controller not involved)
  The OP activity threshold is what separates these two diagnoses.

### Health Score (per loop)
  Sensor issue (frozen PV): 10
  Data quality (compression artefact): 50
  Loop in Manual: max(20, service_factor%)
  Saturation (valve fully open or closed): 25
  Stiction: max(20, 100 - consensus_score)
  Aggressive tuning: 35
  External oscillation: 50
  Sluggish tuning: 35 (55 for borderline sluggish)
  Unresponsive controller: 30
  Signal noise / secondary data quality: 60-70
  Healthy: 100
Secondary issues (oversized valve, quantisation) reduce the score by 10-15 points each on top of the primary.

### Plant Health Index
Weighted average of all loop health scores, where loops with lower health scores contribute proportionally more weight (severity weighting). Displayed as 0-100. >= 75 = Good, 50-74 = Needs Attention, < 50 = Critical.

### IMC-PI Tuning Formulas
lambda (closed-loop speed target) = max(2 x theta, 0.6 x Tu, 0.5 x tau, lambda_floor)
where lambda_floor is a configurable minimum from the tuning config drawer.

FOPDT (first-order process — flow, pressure, temperature loops):
  Kp = tau / (K x (lambda + theta))
  Ti = clamp(tau, 0.5 x tau, 4 x (lambda + theta))

SOPDT (second-order process — detected when >= 50% of OP steps show an inflection point):
  Kp = (tau1 + tau2) / (K x (lambda + theta))
  Ti = tau1 + tau2

Integrating / Level (LC loops — FOPDT does not apply):
  Kp = 1 / (Ki x lambda^2)
  Ti = 2 x lambda
  where Ki = integrating gain estimated from dPV/dt vs OP deviation from steady-state.

When K confidence is Low, the tool anchors the recommendation to the existing estimated Kp with a direction multiplier (increase/decrease) rather than trusting the raw formula-derived number.

### Process Model Parameters
K (process gain) = median(delta_PV / delta_OP) across detected clean OP step windows (|delta_OP| >= 3%, low pre-step variance). PV normalised to 0-100% span first. Falls back to windowed OLS if no clean steps — sets no_excitation = true and suppresses the tuning recommendation.
theta (dead time, min) = lag at peak of OP to PV cross-correlation, converted from samples to minutes.
tau1 (primary time constant, min) = time to reach 63.2% of final delta_PV after a step. Fallbacks: ACF decay rate, or variance ratio method.
tau2 (SOPDT second lag, min) = Broida 2-point method: t1 at 28.3% of delta_PV, t2 at 63.2%; tau_eff = 5.5 x (t2 - t1); tau2 = 0.33 x tau_eff.
Tu (oscillation period) = dominant period from error ACF zero-crossings, in minutes.

### Propagation Scoring
Pairwise between all non-saturating loops. Three components:
  1. Cross-correlation score = |peak correlation coefficient| x 100 (weight 0.4)
  2. Granger causality score = max(0, 100 x (1 - p_value/0.05)) if p < 0.05, else 0 (weight 0.3)
  3. Spectral coherence score (weight 0.3) = fraction of frequency bins where coherence > 0.5, weighted by coherence magnitude, scaled to 0-100.
raw_score = 0.4 x CC_score + 0.3 x Granger_score + 0.3 x coherence_score
combined_score = raw_score x CROSS_UNIT_DOWNWEIGHT (default 0.5) if the two loops are in different plant units; otherwise = raw_score.
Only links with combined_score >= PROP_CONF_MIN (default 60) are reported.
Direction (source to target) is determined by the cross-correlation lag: the loop that leads in time is the source.
