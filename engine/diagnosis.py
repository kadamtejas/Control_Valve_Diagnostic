"""
Diagnosis — the fault decision logic.
=======================================

Layer 2, module 4. Combines metrics, stiction result, performance
indices, oscillation, data quality, and capability flags to produce
a single named diagnosis per loop.

This is the single largest piece of "business logic" in the engine,
and is the most likely place future plant-specific tweaks will land.
"""

from dataclasses import dataclass, field

import numpy as np

from .utils import safe_float, safe_pos
from .data_quality import DataQualityReport
from .capabilities import Capabilities
from .loop_metrics import LoopMetrics
from .stiction_detection import StictionResult
from .time_context import TimeContext


@dataclass
class Diagnosis:
    """End-to-end loop diagnosis combining all indicators."""
    primary: str = "Healthy"          # the most likely problem
    secondary: list = field(default_factory=list)  # additional issues
    confidence: float = 0.0           # 0-100 overall confidence in primary diagnosis
    rationale: str = ""               # plain-language explanation
    detailed_explanation: str = ""    # multi-paragraph in-depth analysis
    health_score: float = 100.0       # 0-100 overall loop health (100 = perfect)
    severity: str = "OK"              # OK / WARN / FAIL / CRITICAL
    recommended_action: str = ""      # maintenance recommendation



def _build_detailed_explanation(diag_type: str, metrics: LoopMetrics,
                                sr: StictionResult, hi: float,
                                osc_reg: float, osc_period: int,
                                dq: DataQualityReport, service_factor: float,
                                capabilities: Capabilities, config: dict,
                                tc: TimeContext) -> str:
    """Build a multi-paragraph detailed explanation for each diagnosis type.

    This produces a thorough, human-readable analysis covering:
      1. WHAT was detected (the key observation)
      2. HOW it was detected (which metrics/methods contributed)
      3. WHY this matters (impact on process performance)
      4. Supporting evidence (numerical values in context)
    """
    lines = []
    hi_str = f"{hi:.3f}" if not np.isnan(hi) else "N/A"
    hi_thr = safe_float(config.get("HARRIS_INDEX_THRESHOLD", 0.3))
    iae_thr = safe_float(config.get("IAE_PER_HOUR_THRESHOLD", 200))
    op_act_thr = safe_float(config.get("OP_ACTIVITY_THRESHOLD", 1.5))
    osc_min = safe_float(config.get("OSCILLATION_REGULARITY_MIN", 0.6))

    # Common metrics block
    def _metrics_block():
        parts = []
        parts.append(f"[Performance Metrics] "
                     f"Harris Index = {hi_str} (threshold {hi_thr:.2f}); "
                     f"IAE/hr = {metrics.iae_per_hour:.1f} (threshold {iae_thr:.0f}); "
                     f"IAE/hr normalised = {metrics.iae_per_hour_norm:.1f}%.")
        parts.append(f"[Controller Output] "
                     f"OP activity (mean |dOP|) = {metrics.op_activity:.3f} (threshold {op_act_thr:.2f}); "
                     f"OP range used = {metrics.op_range_used:.1f}% "
                     f"(min {metrics.op_min:.1f}%, max {metrics.op_max:.1f}%); "
                     f"OP at 0% for {metrics.op_pct_at_zero:.1f}% of time; "
                     f"OP at 100% for {metrics.op_pct_at_full:.1f}% of time.")
        parts.append(f"[Process Variable] "
                     f"PV mean = {metrics.pv_mean:.2f}; "
                     f"PV std = {metrics.pv_std:.3f}; "
                     f"PV amplitude (peak-to-peak) = {metrics.pv_amplitude:.2f} "
                     f"({metrics.pv_amplitude_pct:.1f}% of operating scale).")
        return " ".join(parts)

    def _stiction_block():
        return (f"[Stiction Analysis] "
                f"Consensus score = {sr.consensus_score:.1f}/100 "
                f"({sr.consensus_label}); "
                f"{sr.methods_agreeing} of 4 methods agree (score > 50). "
                f"Individual scores — Heuristic: {sr.heuristic_score:.1f}, "
                f"Horch CC: {sr.horch_score:.1f}, "
                f"Yamashita: {sr.yamashita_score:.1f} (shape: {sr.yamashita_shape}), "
                f"Bicoherence: {sr.bicoherence_score:.1f}. "
                f"Estimated stickband S = {sr.estimated_S:.2f}% OP, "
                f"slip-jump J = {sr.estimated_J:.2f}% OP.")

    def _oscillation_block():
        if np.isnan(osc_reg):
            return "[Oscillation] Hägglund analysis not available."
        period_str = tc.samples_to_display_str(osc_period) if osc_period > 0 else "N/A"
        return (f"[Oscillation Analysis] "
                f"Hägglund regularity = {osc_reg:.3f} (threshold {osc_min:.2f}); "
                f"dominant period = {period_str}. "
                f"Regularity > {osc_min:.1f} indicates a sustained, periodic oscillation "
                f"rather than random disturbance noise.")

    def _dq_block():
        if dq is None:
            return ""
        return (f"[Data Quality] "
                f"Severity: {dq.severity}; "
                f"samples: {dq.n_samples}, finite: {dq.n_finite} "
                f"({dq.pct_missing:.1f}% missing); "
                f"unique PV values: {dq.pv_unique_values}; "
                f"longest frozen run: {dq.longest_frozen_run} samples; "
                f"compression fraction: {dq.compression_fraction:.1%}. "
                + (f"Issues: {'; '.join(dq.issues)}." if dq.issues else "No issues detected."))

    def _service_block():
        return (f"[Service Factor] "
                f"Loop was in AUTO/CAS for {service_factor:.1f}% of the data period "
                f"(threshold {safe_float(config.get('SERVICE_FACTOR_MIN_PCT', 70)):.0f}%). "
                f"Only AUTO/CAS samples are used for performance analysis.")

    # ── Build explanation per diagnosis type ──
    if diag_type == "frozen_sensor":
        lines.append(
            f"FINDING: The PV (process variable) signal is frozen — it held a constant value "
            f"for {dq.longest_frozen_run} consecutive samples "
            f"({tc.samples_to_display_str(dq.longest_frozen_run)}). "
            f"This is far beyond the threshold of "
            f"{int(safe_float(config.get('FROZEN_SAMPLES_MIN', 10)))} samples."
        )
        lines.append(
            "ANALYSIS: A frozen PV almost always indicates a hardware failure — the transmitter "
            "has stopped updating, the I/O card has failed, or a wiring fault has occurred. "
            "In rare cases, a historian compression deadband set too wide can produce the same "
            "artefact. Because the PV is not reflecting the real process value, ALL other "
            "diagnostics (stiction, tuning, oscillation) are unreliable and have been suppressed."
        )
        lines.append(
            "IMPACT: The controller is operating blind — it sees a constant PV and therefore "
            "makes no corrective action. If the actual process variable is drifting, the controller "
            "will not respond, potentially leading to off-spec product, safety hazard, or equipment damage."
        )
        lines.append(_dq_block())

    elif diag_type == "compression":
        lines.append(
            f"FINDING: {int(100*dq.compression_fraction)}% of PV samples are part of compressed "
            f"flat segments (threshold: "
            f"{int(100*safe_float(config.get('COMPRESSION_FLAT_FRACTION_MAX', 0.30)))}%). "
            f"This is characteristic of PI/IP21-style historian compression."
        )
        lines.append(
            "ANALYSIS: Historian data compression works by only recording points when the value "
            "changes by more than a deadband. This creates staircase-like patterns in the data "
            "that can mask true valve behaviour — stiction limit cycles, small oscillations, and "
            "noise signatures are all suppressed. The diagnostic algorithms rely on the temporal "
            "structure of the signal, so compressed data produces unreliable results."
        )
        lines.append(
            "IMPACT: The true performance of this loop cannot be assessed from this data. "
            "Stiction and oscillation scores may be artificially low. The loop may have issues "
            "that are invisible due to compression."
        )
        lines.append(_dq_block())

    elif diag_type == "low_service_factor":
        sf_min = safe_float(config.get("SERVICE_FACTOR_MIN_PCT", 70))
        lines.append(
            f"FINDING: This loop was in AUTO/CAS mode for only {service_factor:.1f}% of the "
            f"data period, which is below the minimum threshold of {sf_min:.0f}%. The loop "
            f"is being operated predominantly in MANUAL mode."
        )
        lines.append(
            "ANALYSIS: When a loop is in MAN, the controller output is fixed by the operator "
            "and the control algorithm is not active. This means the loop's control performance "
            "cannot be meaningfully assessed. A high fraction of time in MAN often indicates "
            "that operators do not trust the controller — common reasons include valve stiction "
            "causing limit cycles in AUTO, poor tuning causing instability, or frequent process "
            "upsets that the controller cannot handle."
        )
        lines.append(
            "IMPACT: Manual operation increases operator workload, reduces consistency, and "
            "eliminates the ability to reject disturbances automatically. Product quality "
            "variability typically increases when loops are run in MAN."
        )
        lines.append(_service_block())
        lines.append(_metrics_block())

    elif diag_type == "saturation_open":
        lines.append(
            f"FINDING: The controller output (OP) is at or above 98% for {metrics.op_pct_at_full:.1f}% "
            f"of the time. The valve is spending a significant fraction of time fully open."
        )
        lines.append(
            "ANALYSIS: When a control valve is fully open, the controller has lost its ability "
            "to increase flow. If the process still demands more flow (PV below SP for a flow "
            "loop, or temperature/pressure not reaching target), the controller saturates and "
            "integral windup may occur. This typically indicates that the valve is undersized "
            "for the current duty, or that upstream supply pressure has dropped."
        )
        lines.append(
            f"The OP ranged from {metrics.op_min:.1f}% to {metrics.op_max:.1f}% "
            f"(used range: {metrics.op_range_used:.1f}%). "
            f"IAE/hr = {metrics.iae_per_hour:.1f}, confirming the controller is struggling "
            f"to maintain setpoint."
        )
        lines.append(
            "IMPACT: The loop cannot control the process variable at its setpoint. This can lead "
            "to off-spec product, energy waste, or unsafe conditions. The valve is at its "
            "physical limit."
        )
        lines.append(_metrics_block())

    elif diag_type == "saturation_closed":
        lines.append(
            f"FINDING: The controller output (OP) is at or below 2% for {metrics.op_pct_at_zero:.1f}% "
            f"of the time. The valve is spending a significant fraction of time fully closed."
        )
        lines.append(
            "ANALYSIS: A valve that is mostly closed may be oversized for the current duty, "
            "or the process load may have changed significantly from the original design. "
            "Operating a valve near its seat for extended periods can cause seat damage and "
            "leakage (passing). In some cases, a closed valve indicates the process has been "
            "shut down or is in a different operating mode."
        )
        lines.append(
            f"The OP ranged from {metrics.op_min:.1f}% to {metrics.op_max:.1f}% "
            f"(used range: {metrics.op_range_used:.1f}%)."
        )
        lines.append(
            "IMPACT: Control authority is lost — the controller cannot reduce flow further. "
            "If the process condition changes and more closure is needed, the valve has no reserve."
        )
        lines.append(_metrics_block())

    elif diag_type == "stiction":
        lines.append(
            f"FINDING: Valve stiction has been detected with a consensus score of "
            f"{sr.consensus_score:.1f}/100, classified as '{sr.consensus_label}'. "
            f"{sr.methods_agreeing} out of 4 independent detection methods agree."
        )
        lines.append(
            "ANALYSIS: Stiction (static friction) occurs when the valve stem and packing "
            "bind together, requiring an excess force (the 'stickband') to initiate movement. "
            "Once the static friction is overcome, the valve jumps to a new position (the "
            "'slip-jump'). This creates a characteristic limit cycle: the controller winds up "
            "its output while the valve is stuck, then the valve suddenly moves, overshooting "
            "the target, and the cycle repeats."
        )
        lines.append(
            f"METHOD DETAILS: "
            f"(1) Heuristic score = {sr.heuristic_score:.1f}/100 — weighted combination of "
            f"OP activity, PV amplitude, IAE, and OP reversals. "
            f"(2) Horch CC score = {sr.horch_score:.1f}/100 — measures asymmetry of the "
            f"OP-PV cross-correlation function; stiction causes time-shifted, asymmetric coupling. "
            f"(3) Yamashita score = {sr.yamashita_score:.1f}/100 — classifies the PV-vs-OP "
            f"scatter plot shape (detected: '{sr.yamashita_shape}'); a parallelogram with sharp "
            f"corners indicates stiction, an ellipse indicates hysteresis/backlash. "
            f"(4) Bicoherence score = {sr.bicoherence_score:.1f}/100 — detects non-linear "
            f"harmonic coupling in the PV frequency spectrum; stiction produces characteristic "
            f"higher harmonics that a linear process would not."
        )
        lines.append(
            f"ESTIMATED PARAMETERS: Stickband S = {sr.estimated_S:.2f}% OP — this is the "
            f"minimum change in controller output required before the valve begins to move. "
            f"Slip-jump J = {sr.estimated_J:.2f}% OP — this is how far the valve overshoots "
            f"when it breaks free. These values are estimated using the Rossi-Scali method "
            f"by analysing OP reversal segments where PV remains flat."
        )
        lines.append(
            "IMPACT: Stiction causes persistent oscillations that degrade product quality, "
            "increase energy consumption, and propagate disturbances to downstream loops. "
            "The oscillation cannot be eliminated by re-tuning — it requires mechanical "
            "intervention on the valve."
        )
        lines.append(_metrics_block())

    elif diag_type == "aggressive_tuning":
        period_str = tc.samples_to_display_str(osc_period) if osc_period > 0 else "N/A"
        lines.append(
            f"FINDING: The loop exhibits sustained oscillation with period ≈ {period_str} "
            f"and Hägglund regularity = {osc_reg:.3f} (threshold {osc_min:.2f}). The controller "
            f"output is actively moving (OP activity = {metrics.op_activity:.3f}), confirming "
            f"the controller is driving the oscillation."
        )
        lines.append(
            "ANALYSIS: Aggressive (over-tuned) controller settings cause the loop to oscillate "
            "because the controller overreacts to each deviation. The gain is too high and/or "
            "the integral time is too short, causing the controller to overshoot the setpoint "
            "in each correction. The key indicator is that BOTH OP and PV are oscillating "
            "together — the controller is the source, not an external disturbance."
        )
        lines.append(
            f"Harris Index = {hi_str} (threshold {hi_thr:.2f}). A low Harris Index confirms "
            f"that the actual variance is much larger than the minimum achievable variance, "
            f"meaning the controller is performing poorly. The PV amplitude is "
            f"{metrics.pv_amplitude:.2f} ({metrics.pv_amplitude_pct:.1f}% of scale), "
            f"which is significant enough to affect process quality."
        )
        lines.append(
            "IMPACT: Aggressive tuning causes unnecessary valve wear due to constant movement, "
            "increased variability in the controlled variable, and can propagate oscillations "
            "to other loops in the plant through process interactions."
        )
        lines.append(_oscillation_block())
        lines.append(_metrics_block())

    elif diag_type == "external_oscillation":
        period_str = tc.samples_to_display_str(osc_period) if osc_period > 0 else "N/A"
        lines.append(
            f"FINDING: The PV is oscillating regularly (period ≈ {period_str}, regularity "
            f"= {osc_reg:.3f}) but the controller output is barely moving (OP activity "
            f"= {metrics.op_activity:.3f}). This dissociation between PV oscillation and "
            f"OP stillness indicates the oscillation source is EXTERNAL to this loop."
        )
        lines.append(
            "ANALYSIS: When PV oscillates but OP does not, the disturbance is entering the "
            "process through an upstream or interacting loop, not through this valve. The "
            "controller may be too detuned to reject it, or the disturbance frequency may be "
            "too fast for the control loop's bandwidth. Re-tuning THIS controller will not "
            "fix the problem — the root cause is elsewhere in the plant."
        )
        lines.append(
            f"Harris Index = {hi_str}, confirming poor variance reduction. The controller "
            f"is not compensating for the incoming disturbance."
        )
        lines.append(
            "IMPACT: The PV deviates from setpoint due to a disturbance that this controller "
            "cannot reject. To fix this, trace the oscillation upstream using the Propagation "
            "analysis sheet — look for loops oscillating at the same period."
        )
        lines.append(_oscillation_block())
        lines.append(_metrics_block())

    elif diag_type == "sluggish_tuning":
        lines.append(
            f"FINDING: The controller is too detuned — Harris Index = {hi_str} "
            f"(threshold {hi_thr:.2f}) and IAE/hr = {metrics.iae_per_hour:.1f} "
            f"(threshold {iae_thr:.0f}), yet OP activity is low at "
            f"{metrics.op_activity:.3f} (threshold {op_act_thr:.2f})."
        )
        lines.append(
            "ANALYSIS: A sluggish controller responds too slowly to disturbances or setpoint "
            "changes. The gain (Kc) is too low and/or the integral time (Ti) is too long. "
            "The controller is not moving the valve aggressively enough to keep PV close to SP. "
            "Unlike aggressive tuning, there is no regular oscillation — the PV simply drifts "
            "away from SP and returns slowly."
        )
        lines.append(
            f"The low OP activity ({metrics.op_activity:.3f}) combined with high IAE "
            f"({metrics.iae_per_hour:.1f}/hr) is the classic signature: the controller is "
            f"barely moving the valve while the error accumulates."
        )
        lines.append(
            "IMPACT: Sluggish control leads to poor disturbance rejection, slow recovery from "
            "upsets, and unnecessarily wide variability in the controlled variable. Product "
            "quality suffers, and operators may put the loop in MAN out of frustration."
        )
        lines.append(_metrics_block())

    elif diag_type == "unresponsive":
        lines.append(
            f"FINDING: The controller output is essentially static (OP activity = "
            f"{metrics.op_activity:.4f}, OP range used = {metrics.op_range_used:.1f}%) "
            f"while the PV is clearly varying (PV std = {metrics.pv_std:.3f}, amplitude "
            f"= {metrics.pv_amplitude:.2f} = {metrics.pv_amplitude_pct:.1f}% of scale)."
        )
        lines.append(
            "ANALYSIS: An unresponsive controller is one that is not adjusting the valve at "
            "all despite seeing PV deviations from SP. Possible root causes include: "
            "(a) The controller may be in a pseudo-AUTO mode where the output is clamped by "
            "output limits or rate limits set too tight. "
            "(b) The actuator or positioner may have a mechanical failure preventing valve "
            "movement even though the controller is sending a signal. "
            "(c) The controller gain may be essentially zero, or integral action disabled. "
            "(d) The PV input to the controller may be different from the PV we are reading "
            "(e.g., signal selector or override logic is active)."
        )
        lines.append(
            f"Harris Index = {hi_str if not np.isnan(hi) else 'N/A (OP too static for reliable estimation)'}. "
            f"IAE/hr = {metrics.iae_per_hour:.1f} "
            f"(normalised {metrics.iae_per_hour_norm:.1f}% of PV operating range)."
        )
        lines.append(
            "IMPACT: The process variable is uncontrolled — it is subject to whatever "
            "disturbances the process imposes, with no corrective action from the controller. "
            "This is functionally equivalent to having the loop in MAN with a fixed output."
        )
        lines.append(_metrics_block())
        lines.append(_dq_block())

    elif diag_type == "healthy":
        lines.append(
            "FINDING: No fault signature was detected. All diagnostic checks returned values "
            "within acceptable thresholds."
        )
        summary_parts = []
        if not np.isnan(hi):
            if hi >= 0.5:
                summary_parts.append(f"Harris Index = {hi_str} (good — above 0.5, indicating "
                                     f"the controller is achieving close to minimum variance)")
            else:
                summary_parts.append(f"Harris Index = {hi_str} (below 0.5 but above the fault "
                                     f"threshold of {hi_thr:.2f}; control could be improved but "
                                     f"is not classified as a problem)")
        if not np.isnan(osc_reg):
            if osc_reg < osc_min:
                summary_parts.append(f"Hägglund regularity = {osc_reg:.3f} (below {osc_min:.2f} "
                                     f"— no sustained oscillation detected)")
            else:
                summary_parts.append(f"Hägglund regularity = {osc_reg:.3f} (oscillation present "
                                     f"but amplitude too small to be a concern)")
        summary_parts.append(f"IAE/hr = {metrics.iae_per_hour:.1f}")
        summary_parts.append(f"OP activity = {metrics.op_activity:.3f}")
        summary_parts.append(f"PV amplitude = {metrics.pv_amplitude:.2f} "
                             f"({metrics.pv_amplitude_pct:.1f}% of scale)")
        lines.append("ANALYSIS: " + ". ".join(summary_parts) + ".")
        if sr.consensus_score > 0:
            lines.append(
                f"Stiction consensus = {sr.consensus_score:.1f}/100 ({sr.consensus_label}) — "
                f"below the threshold for a stiction diagnosis."
            )
        lines.append(
            "CONCLUSION: The loop is performing within acceptable limits. Continue routine "
            "monitoring. If process conditions change, re-run diagnostics to verify."
        )
        lines.append(_metrics_block())
    else:
        lines.append(_metrics_block())
        lines.append(_dq_block())

    return "\n\n".join(l for l in lines if l)


def diagnose_loop(metrics: LoopMetrics, sr: StictionResult, hi: float,
                  osc_reg: float, osc_period: int, dq: DataQualityReport,
                  service_factor: float, capabilities: Capabilities,
                  config: dict, tc: TimeContext,
                  selection=None) -> Diagnosis:
    """
    Multi-class diagnosis using priority-ordered checks. The first matching
    rule wins for `primary`, but other observed issues are listed as
    `secondary`. Health score is built up additively from all findings.
    """
    diag = Diagnosis()
    health = 100.0
    secondary = []

    sf_min = safe_float(config.get("SERVICE_FACTOR_MIN_PCT", 70))
    hi_thr = safe_float(config.get("HARRIS_INDEX_THRESHOLD", 0.3))
    osc_min = safe_float(config.get("OSCILLATION_REGULARITY_MIN", 0.6))
    iae_thr = safe_float(config.get("IAE_PER_HOUR_THRESHOLD", 200))
    op_act_thr = safe_float(config.get("OP_ACTIVITY_THRESHOLD", 1.5))
    s_min = safe_float(config.get("STICTION_S_MIN_PCT", 0.5))

    # ── Priority 1: data quality kills everything ───────────────────
    if dq.is_frozen:
        diag.primary = "Sensor issue (frozen PV)"
        diag.severity = "FAIL"
        diag.confidence = 95.0
        diag.health_score = 10.0
        diag.rationale = (f"PV held a single value for {dq.longest_frozen_run} "
                          f"consecutive samples ({tc.samples_to_display_str(dq.longest_frozen_run)}). "
                          "All other diagnostics suppressed.")
        diag.recommended_action = ("Investigate transmitter / I/O card. "
                                   "Other diagnostics on this loop are unreliable until the sensor is fixed.")
        return diag

    if dq.is_compressed:
        diag.primary = "Data quality (compression artefact)"
        diag.severity = "WARN"
        diag.confidence = 80.0
        diag.health_score = 50.0
        diag.rationale = (f"{int(100*dq.compression_fraction)}% of PV samples are "
                          "part of compressed flat segments — historian compression "
                          "may be hiding true valve behaviour.")
        diag.recommended_action = ("Reduce historian compression deadband for this tag, "
                                   "or pull data via a less-compressed source, then re-run.")
        return diag

    if dq.is_quantised:
        secondary.append(f"PV is quantised to {dq.pv_unique_values} unique values")
        health -= 15

    # ── Priority 2: service factor ──────────────────────────────────
    if service_factor < sf_min:
        diag.primary = "Loop in MAN (low service factor)"
        diag.severity = "WARN"
        diag.confidence = 95.0
        diag.health_score = max(20.0, service_factor)
        diag.rationale = (f"Loop was in AUTO/CAS only {service_factor:.0f}% of the time "
                          f"(threshold {sf_min:.0f}%). Operator override is hiding control performance.")
        diag.recommended_action = ("Investigate why operators are running this loop in MAN. "
                                   "Common causes: stiction, bad tuning, or process upset.")
        return diag

    # ── Priority 3: saturation ──────────────────────────────────────
    if metrics.op_pct_at_full > 30:
        diag.primary = "Saturation (valve fully open)"
        diag.severity = "FAIL"
        diag.confidence = 92.0
        diag.health_score = 25.0
        diag.rationale = (f"OP at >98% for {metrics.op_pct_at_full:.0f}% of the time. "
                          "Valve cannot deliver demanded flow.")
        diag.recommended_action = ("Check upstream pressure / supply. If chronic, valve is "
                                   "undersized for the duty — consider Cv increase or trim change.")
        return diag
    if metrics.op_pct_at_zero > 30:
        diag.primary = "Saturation (valve fully closed)"
        diag.severity = "FAIL"
        diag.confidence = 92.0
        diag.health_score = 25.0
        diag.rationale = (f"OP at <2% for {metrics.op_pct_at_zero:.0f}% of the time. "
                          "Valve sized for very different duty, or process load changed.")
        diag.recommended_action = ("Re-evaluate valve sizing. If shut for long periods, "
                                   "check seat tightness (passing valve) on next opportunity.")
        return diag

    # ── Priority 4: oversized valve (operates in a tiny band) ───────
    if metrics.op_range_used < 5.0 and not metrics.saturated:
        secondary.append(f"OP only varies {metrics.op_range_used:.1f}% (possible oversized valve)")
        health -= 10

    # ── Priority 5: stiction (only if data supports it AND user wants it) ─
    stiction_likely = False
    stiction_enabled = (selection is None) or selection.stiction_detection
    if capabilities.can_stiction and stiction_enabled:
        if sr.consensus_label == "Confirmed":
            stiction_likely = True
            diag.primary = "Valve stiction (Confirmed)"
            diag.severity = "FAIL"
            diag.confidence = sr.consensus_score
        elif sr.consensus_label == "Likely" and sr.estimated_S >= s_min:
            stiction_likely = True
            diag.primary = "Valve stiction (Likely)"
            diag.severity = "WARN"
            diag.confidence = sr.consensus_score
        elif sr.consensus_label == "Possible" and sr.estimated_S >= s_min and \
             sr.methods_agreeing >= 2:
            stiction_likely = True
            diag.primary = "Valve stiction (Possible)"
            diag.severity = "WARN"
            diag.confidence = sr.consensus_score

    if stiction_likely:
        diag.health_score = max(20.0, 100.0 - sr.consensus_score)
        diag.rationale = (
            f"Stiction consensus score {sr.consensus_score:.0f}/100 from "
            f"{sr.methods_agreeing} of 4 methods. Estimated S = {sr.estimated_S:.2f}% OP, "
            f"J = {sr.estimated_J:.2f}% OP. PV-OP shape: {sr.yamashita_shape}."
        )
        diag.recommended_action = (
            "Schedule valve service: clean stem/packing, check actuator, "
            "calibrate positioner. If positioner is older PP/I-P, consider digital upgrade."
        )
        diag.detailed_explanation = _build_detailed_explanation(
            "stiction", metrics, sr, hi, osc_reg, osc_period, dq,
            service_factor, capabilities, config, tc)
        return diag

    # ── Priority 6: Oscillation diagnoses ───────────────────────────
    # Use a RELATIVE amplitude (% of PV mean) so the test works at any scale.
    # A loop with PV peak-to-peak > 5% of its operating value is meaningfully
    # oscillating, regardless of whether PV reads in barg, °C, or m³/h.
    osc_amp_significant = (
        metrics.pv_amplitude_pct > 5.0
        or metrics.pv_amplitude > 5.0   # absolute fallback
    )
    is_oscillating = (
        capabilities.can_oscillation
        and osc_reg >= osc_min
        and osc_amp_significant
    )

    # User-selection gates for the diagnoses below
    aggressive_enabled = (selection is None) or selection.aggressive_tuning
    external_enabled = (selection is None) or selection.external_oscillation
    sluggish_enabled = (selection is None) or selection.sluggish_tuning

    # Aggressive tuning: regular oscillation + OP moving meaningfully (controller fighting).
    # Use a softer OP-activity threshold when oscillation regularity is high — a perfect
    # limit cycle with op_activity slightly under threshold is still aggressive.
    op_active_for_osc = (
        metrics.op_activity > op_act_thr
        or (osc_reg >= 0.85 and metrics.op_activity > op_act_thr * 0.5)
    )
    if (aggressive_enabled
            and is_oscillating
            and op_active_for_osc
            and not np.isnan(hi) and hi < hi_thr):
        diag.primary = "Aggressive tuning (oscillation)"
        diag.severity = "WARN"
        diag.confidence = 80.0
        diag.health_score = 35.0
        period_str = tc.samples_to_display_str(osc_period) if osc_period > 0 else "?"
        diag.rationale = (
            f"Sustained oscillation, period ≈ {period_str}, regularity {osc_reg:.2f}. "
            f"Harris Index {hi:.2f} (threshold {hi_thr:.2f}), OP activity {metrics.op_activity:.2f}. "
            "OP is moving in step with PV — controller is the cause."
        )
        diag.recommended_action = (
            "Re-tune controller — try lambda tuning or ITAE-optimal PI. "
            "Verify in MAN that the oscillation disappears (confirms tuning, not valve)."
        )
        diag.detailed_explanation = _build_detailed_explanation(
            "aggressive_tuning", metrics, sr, hi, osc_reg, osc_period, dq,
            service_factor, capabilities, config, tc)
        return diag

    # External / propagated oscillation: regular oscillation + LOW OP activity +
    # poor Harris. The valve is NOT moving much, but PV is still oscillating
    # regularly. Only call this when regularity is HIGH (>0.85) — moderate
    # regularity with low OP activity is more likely sluggish tuning.
    if (external_enabled
            and is_oscillating
            and osc_reg >= 0.85
            and metrics.op_activity < op_act_thr * 0.3
            and not np.isnan(hi) and hi < hi_thr):
        diag.primary = "External oscillation (upstream / disturbance)"
        diag.severity = "WARN"
        diag.confidence = 75.0
        diag.health_score = 50.0
        period_str = tc.samples_to_display_str(osc_period) if osc_period > 0 else "?"
        diag.rationale = (
            f"PV oscillates regularly (period ≈ {period_str}, regularity {osc_reg:.2f}, "
            f"Harris {hi:.2f}) but OP activity is small ({metrics.op_activity:.2f}). "
            "Controller is not the source — disturbance is propagating in from upstream."
        )
        diag.recommended_action = (
            "Trace the disturbance source via the Propagation sheet. Look for upstream "
            "loops oscillating at the same period. Fixing this loop's tuning will not help."
        )
        diag.detailed_explanation = _build_detailed_explanation(
            "external_oscillation", metrics, sr, hi, osc_reg, osc_period, dq,
            service_factor, capabilities, config, tc)
        return diag

    # ── Priority 7: sluggish tuning ─────────────────────────────────
    # Sluggish = controller is barely moving (OP activity low) but performance
    # is bad (Harris low, IAE high). Whether the resulting PV looks oscillatory
    # because of disturbances is irrelevant — the cause is the same.
    if (sluggish_enabled
            and not np.isnan(hi) and hi < hi_thr
            and metrics.iae_per_hour > iae_thr
            and metrics.op_activity < op_act_thr):
        diag.primary = "Sluggish tuning"
        diag.severity = "WARN"
        diag.confidence = 75.0
        diag.health_score = 45.0
        diag.rationale = (
            f"Harris Index {hi:.2f} indicates poor variance reduction; IAE/hr "
            f"{metrics.iae_per_hour:.0f} > {iae_thr:.0f}. OP activity is low "
            f"({metrics.op_activity:.2f}) — the controller is too detuned to "
            "reject disturbances or follow setpoint changes."
        )
        diag.recommended_action = (
            "Increase controller gain (Kc) or shorten Ti. Verify controller is not "
            "in P-only mode by mistake. Consider a step test for re-tuning."
        )
        diag.detailed_explanation = _build_detailed_explanation(
            "sluggish_tuning", metrics, sr, hi, osc_reg, osc_period, dq,
            service_factor, capabilities, config, tc)
        return diag

    # ── Priority 7b: unresponsive controller ─────────────────────────
    # Controller output is nearly static while PV deviates from SP.
    # This catches loops where Harris is NaN (invalidated due to static OP)
    # or unreliable, and the absolute IAE threshold is too high for the
    # scale. Uses the normalised IAE (% of PV operating range) instead.
    iae_norm_thr = safe_float(config.get("IAE_NORM_THRESHOLD_PCT", 15.0))
    if (metrics.op_activity < op_act_thr * 0.05        # OP essentially static
            and metrics.pv_std > 0.3                   # PV is varying
            and metrics.pv_amplitude_pct > 3.0):       # meaningful PV swing relative to scale
        diag.primary = "Unresponsive controller"
        diag.severity = "WARN"
        diag.confidence = 85.0
        diag.health_score = 40.0
        hi_str = f"{hi:.2f}" if not np.isnan(hi) else "N/A (OP too static)"
        diag.rationale = (
            f"Controller output is nearly static (OP activity {metrics.op_activity:.4f}, "
            f"range {metrics.op_range_used:.1f}%) while PV deviates from SP "
            f"(PV std {metrics.pv_std:.2f}, amplitude {metrics.pv_amplitude:.1f} = "
            f"{metrics.pv_amplitude_pct:.1f}% of scale). "
            f"Harris Index {hi_str}. IAE/hr {metrics.iae_per_hour:.0f} "
            f"(normalised {metrics.iae_per_hour_norm:.1f}%). "
            "The controller is not adjusting the valve to reject disturbances."
        )
        diag.recommended_action = (
            "Check that the controller is actually in AUTO and receiving the PV signal. "
            "Verify controller output limits are not clamped. If output is genuinely "
            "limited, investigate actuator/positioner for mechanical binding. "
            "Re-tune controller: increase gain (Kc) or shorten integral time (Ti)."
        )
        diag.detailed_explanation = _build_detailed_explanation(
            "unresponsive", metrics, sr, hi, osc_reg, osc_period, dq,
            service_factor, capabilities, config, tc)
        return diag

    # ── Priority 8: external disturbance / propagation ──────────────
    # (will be filled in by the propagation post-processing step.)

    # ── Healthy ─────────────────────────────────────────────────────
    diag.primary = "Healthy"
    diag.severity = "OK"
    diag.confidence = 90.0
    diag.health_score = max(50.0, health)
    hi_str = f"{hi:.2f}" if not np.isnan(hi) else "N/A"
    diag.rationale = (
        f"Harris {hi_str}, IAE/hr {metrics.iae_per_hour:.0f}, OP activity "
        f"{metrics.op_activity:.2f}. No fault signature triggered."
    )
    diag.recommended_action = "Continue routine monitoring."
    if secondary:
        diag.secondary = secondary
        diag.health_score -= 5 * len(secondary)
    diag.detailed_explanation = _build_detailed_explanation(
        "healthy", metrics, sr, hi, osc_reg, osc_period, dq,
        service_factor, capabilities, config, tc)
    return diag
