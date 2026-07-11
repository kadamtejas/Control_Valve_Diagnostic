"""
Stiction detection — four independent detectors plus consensus.
=================================================================

Layer 2, module 3. Independent stiction detection methods that vote:

  * heuristic         — classical Choudhury/Shah triangular-shape test
  * Horch             — cross-correlation OP↔PV asymmetry
  * Yamashita         — PV-OP cycle shape (gas-liquid loops)
  * bicoherence       — frequency-domain non-linearity test

The consensus combiner produces a final label and confidence. Also
includes Rossi-Scali parameter estimation (S, J).
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .utils import safe_float, safe_pos, DEFAULTS
from .loop_metrics import LoopMetrics


@dataclass
class StictionResult:
    heuristic_score: float = 0.0       # 0–100
    horch_score: float = 0.0           # 0–100
    yamashita_score: float = 0.0       # 0–100
    bicoherence_score: float = 0.0     # 0–100
    consensus_score: float = 0.0       # 0–100, weighted average
    consensus_label: str = "Healthy"   # Healthy / Possible / Likely / Confirmed
    estimated_S: Optional[float] = None  # Rossi-Scali stickband, OP% (None = no valid segment found)
    estimated_J: Optional[float] = None  # Rossi-Scali slip-jump, OP% (None = no valid segment found)
    yamashita_shape: str = "unknown"   # "straight" / "ellipse" / "parallelogram" / "unknown"
    methods_agreeing: int = 0


# ─── Method 1: heuristic (kept from v1, somewhat refactored) ───────────
def stiction_heuristic(pv, op, sp, op_activity, pv_amp, iae_per_hour,
                       config) -> float:
    """Heuristic weighted score using OP activity, PV amplitude, IAE, OP reversals.
    Soft saturation: a metric at 1× threshold contributes ~50; at 3×, ~85."""
    n = len(pv)
    def soft(x, thr):
        # sigmoid-like: 0 at 0, 50 at thr, asymptotic to 100
        if thr <= 0:
            return 0.0
        r = x / thr
        return 100.0 * r / (r + 1.0)

    op_part = soft(op_activity, safe_pos(config.get("OP_ACTIVITY_THRESHOLD", 1.5)))
    amp_part = soft(pv_amp, safe_pos(config.get("AMP_THRESHOLD", 15.0)))
    iae_part = soft(iae_per_hour, safe_pos(config.get("IAE_PER_HOUR_THRESHOLD", 200.0)))
    if n > 1:
        sign_changes = int(np.sum(np.diff(np.sign(np.diff(op))) != 0))
        rev_per_sample = sign_changes / max(n, 1)
        rev_part = soft(rev_per_sample, 0.1)
    else:
        rev_part = 0.0
    score = 0.40 * op_part + 0.25 * amp_part + 0.20 * iae_part + 0.15 * rev_part
    return round(min(score, 100.0), 1)


# ─── Method 2: Horch's cross-correlation method (1999) ─────────────────
def stiction_horch(pv: np.ndarray, op: np.ndarray) -> float:
    """
    Horch (1999): Under no stiction, the cross-correlation r_{OP,PV}(τ) is
    even-symmetric (peak at τ=0 for proportional process). Under stiction,
    OP and PV move at different times — CC becomes asymmetric.

    Test statistic: ratio of the *odd* part of r_{OP,PV} energy to total
    energy. Higher = more asymmetry = more stiction-like.
    Returns 0–100 score.
    """
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)
    pv = pv - np.mean(pv)
    op = op - np.mean(op)
    if np.std(pv) < 1e-9 or np.std(op) < 1e-9 or len(pv) < 30:
        return 0.0
    n = len(pv)
    max_lag = min(n // 4, 50)
    lags = np.arange(-max_lag, max_lag + 1)
    cc = np.array([
        np.dot(pv[max(0, k):n + min(0, k)], op[max(0, -k):n + min(0, -k)])
        / (n - abs(k))
        for k in lags
    ])
    cc /= max(np.std(pv) * np.std(op), 1e-9)
    # Decompose into even and odd parts
    cc_even = 0.5 * (cc + cc[::-1])
    cc_odd = 0.5 * (cc - cc[::-1])
    energy_total = np.sum(cc ** 2) + 1e-9
    energy_odd = np.sum(cc_odd ** 2)
    asym_ratio = energy_odd / energy_total
    # Empirically calibrate: 0 → healthy, 0.5 → strong stiction
    score = min(asym_ratio / 0.5, 1.0) * 100
    return round(score, 1)


# ─── Method 3: Yamashita PV-OP shape classifier ────────────────────────
def stiction_yamashita(pv: np.ndarray, op: np.ndarray) -> tuple:
    """
    Examine the PV-vs-OP plot.
      • Straight cluster → healthy
      • Ellipse (open loop)→ backlash / hysteresis
      • Parallelogram (sharp corners)→ stiction
    Implementation: detect path reversals; at each reversal estimate the
    "corner sharpness". Sharp corners (small radius of curvature) → stiction.
    Round corners → backlash. Linear scatter → healthy.
    Uses range-normalised coords so the test is gain-independent.
    """
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)
    if len(pv) < 50 or np.std(pv) < 1e-6 or np.std(op) < 1e-6:
        return 0.0, "unknown"

    # Range-normalise to [0, 1] so geometric measures are comparable
    pv_rng = max(np.ptp(pv), 1e-6)
    op_rng = max(np.ptp(op), 1e-6)
    pv_n = (pv - np.min(pv)) / pv_rng
    op_n = (op - np.min(op)) / op_rng

    # Linear fit and perpendicular scatter
    if np.std(op_n) < 1e-6:
        return 0.0, "unknown"
    coef = np.polyfit(op_n, pv_n, 1)
    pv_pred = np.polyval(coef, op_n)
    residual = pv_n - pv_pred
    perp_scatter = float(np.std(residual))   # range-normalised, in [0, ~0.5]

    # Hysteresis area (signed): how much loop area is enclosed
    # Normalised by the range×range (so it's dimensionless, in [0, 1])
    if len(op_n) > 2:
        signed_area = 0.5 * np.abs(np.sum(op_n[:-1] * pv_n[1:] - op_n[1:] * pv_n[:-1]))
        # area is in (op_n × pv_n) units; divide by N to get "per pair"
        # Actually for shape characterization: divide by the total path length
        path_len = np.sum(np.sqrt(np.diff(op_n) ** 2 + np.diff(pv_n) ** 2))
        if path_len > 1e-6:
            shape_loopiness = signed_area / path_len
        else:
            shape_loopiness = 0.0
    else:
        shape_loopiness = 0.0

    # Corner sharpness at OP-direction reversals
    op_d = np.diff(op_n)
    sign = np.sign(op_d)
    sign[sign == 0] = 1
    reversals = np.where(np.diff(sign) != 0)[0]
    sharp_count = 0
    smooth_count = 0
    look = 5
    for r in reversals:
        if r < look or r > len(op_n) - look - 1:
            continue
        v_in = np.array([op_n[r] - op_n[r - look], pv_n[r] - pv_n[r - look]])
        v_out = np.array([op_n[r + look] - op_n[r], pv_n[r + look] - pv_n[r]])
        nin = np.linalg.norm(v_in)
        nout = np.linalg.norm(v_out)
        if nin < 1e-9 or nout < 1e-9:
            continue
        cos_angle = float(np.dot(v_in, v_out) / (nin * nout))
        cos_angle = max(-1.0, min(1.0, cos_angle))
        # sharp 180° turn ⇒ cos_angle ≈ -1
        if cos_angle < -0.5:
            sharp_count += 1
        elif cos_angle > 0.3:
            smooth_count += 1

    total_corners = sharp_count + smooth_count

    # Decision logic. Calibrated so a healthy linear loop scores LOW.
    if perp_scatter < 0.12 and shape_loopiness < 0.02:
        # Tight straight line — clearly healthy
        return 0.0, "straight"
    if total_corners < 3:
        # Too few reversals to detect stiction by shape
        return 0.0, "insufficient_reversals"
    sharp_frac = sharp_count / total_corners
    if sharp_frac > 0.5 and shape_loopiness > 0.04:
        # Many sharp reversals + finite area → parallelogram → stiction
        score = 60.0 + 35.0 * sharp_frac
        return round(min(score, 95.0), 1), "parallelogram"
    if shape_loopiness > 0.05 and sharp_frac < 0.3:
        return 45.0, "ellipse"
    return round(20 + 30 * sharp_frac, 1), "unclear"


# ─── Method 4: Bicoherence (non-linearity index, simplified) ───────────
def stiction_bicoherence(pv: np.ndarray) -> float:
    """
    Choudhury-style non-linearity test.
    Compute the bicoherence b(f1, f2) = |E[X(f1)X(f2)X*(f1+f2)]|² /
                                        E[|X(f1)X(f2)|²] · E[|X(f1+f2)|²]
    A linear Gaussian process has bicoherence = 0 everywhere.
    Stiction creates harmonics → non-zero bicoherence at harmonic-related
    frequency pairs. Return mean bicoherence above a noise threshold,
    scaled to 0–100.
    """
    pv = np.asarray(pv, dtype=float)
    pv = pv[np.isfinite(pv)]
    if len(pv) < 256:
        return 0.0
    # Center
    pv = pv - np.mean(pv)
    if np.std(pv) < 1e-9:
        return 0.0
    # Segment into overlapping FFT windows
    nfft = min(128, len(pv) // 4)
    nfft = max(64, nfft)
    if nfft & 1:
        nfft += 1
    hop = nfft // 2
    window = np.hanning(nfft)
    segs = []
    for start in range(0, len(pv) - nfft, hop):
        seg = pv[start: start + nfft] * window
        segs.append(np.fft.rfft(seg))
    if len(segs) < 8:
        return 0.0
    X = np.array(segs)               # (n_seg, n_freq)
    K = X.shape[1]
    K_use = min(K, 32)               # only low-frequency band has SNR

    # Compute bicoherence over (f1, f2) where f1+f2 < K
    num = np.zeros((K_use, K_use), dtype=complex)
    den1 = np.zeros((K_use, K_use))
    den2 = np.zeros((K_use, K_use))
    for f1 in range(K_use):
        for f2 in range(K_use - f1):
            triple = X[:, f1] * X[:, f2] * np.conj(X[:, f1 + f2])
            num[f1, f2] = np.mean(triple)
            den1[f1, f2] = np.mean(np.abs(X[:, f1] * X[:, f2]) ** 2)
            den2[f1, f2] = np.mean(np.abs(X[:, f1 + f2]) ** 2)
    bicoh2 = np.abs(num) ** 2 / (den1 * den2 + 1e-12)
    bicoh2 = np.where(np.isfinite(bicoh2), bicoh2, 0.0)
    # Test: fraction of bins with bicoh > threshold (95% confidence ≈ 6/n_seg)
    thr = 6.0 / len(segs)
    significant_mask = bicoh2 > thr
    # Mass and peak of bicoherence over significant bins
    if np.any(significant_mask):
        nlf = float(np.mean(bicoh2[significant_mask]))
        sig_frac = float(np.mean(significant_mask))
    else:
        nlf, sig_frac = 0.0, 0.0
    # Combined: require both elevated mean AND a meaningful fraction of
    # significant bins to score high. Linear Gaussian noise → ~0; clear
    # harmonic non-linearity (stiction) → scores 60-80.
    score = (min(nlf / 0.5, 1.0) * 50.0 +
             min(sig_frac / 0.15, 1.0) * 30.0)
    return round(min(score, 80.0), 1)


# ─── Rossi-Scali parameter estimation (S, J) ───────────────────────────
def estimate_stiction_parameters(pv: np.ndarray, op: np.ndarray, config: dict = None) -> tuple:
    """
    Estimate stickband S and slip-jump J in OP%.
    Method: identify reversal segments where PV stays flat while OP keeps
    moving; the OP excursion before PV starts moving is S. The PV jump
    when motion resumes maps back to a J estimate via the local OP-PV gain.
    Returns (S_pct, J_pct), or (None, None) if no valid segment is found.

    Uses a trailing (causal) rolling mean to detect PV movement so the
    "did PV move after this reversal" test never looks ahead of the
    reversal point — a centered window would leak future PV samples
    backward and make PV appear to move before it actually did.

    The minimum segment length (in samples) is config-driven via
    STICTION_MIN_SEGMENT_SAMPLES rather than a fixed constant, since a
    sensible minimum depends on the loop's cycling speed relative to the
    historian's sample interval — not a fixed number of samples.
    """
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)
    if len(pv) < 50:
        return None, None

    op_d = np.diff(op)
    sign = np.sign(op_d)
    sign[sign == 0] = 0
    # find "OP-moving" segments and "OP-still" segments
    reversal_idx = np.where(np.diff(sign) != 0)[0]
    if len(reversal_idx) < 4:
        return None, None

    pv_smooth = pd.Series(pv).rolling(5, center=False, min_periods=1).mean().values
    pv_d = np.diff(pv_smooth)

    S_estimates = []
    J_estimates = []
    pv_amp_total = float(np.std(pv)) + 1e-9
    pv_threshold = 0.5 * pv_amp_total / 5
    cfg = config or {}
    min_seg = int(safe_float(cfg.get("STICTION_MIN_SEGMENT_SAMPLES",
                                      DEFAULTS.get("STICTION_MIN_SEGMENT_SAMPLES", 3))))

    for k in range(len(reversal_idx) - 1):
        r1 = reversal_idx[k]
        r2 = reversal_idx[k + 1]
        if r2 - r1 < min_seg:
            continue
        op_segment = op[r1: r2]
        pv_segment = pv_d[r1: r2]
        # Find first index where PV starts moving > threshold
        pv_moves = np.where(np.abs(pv_segment) > pv_threshold)[0]
        if len(pv_moves) == 0:
            continue
        first_move = pv_moves[0]
        if first_move == 0:
            # PV was already moving in the very first sample after the
            # reversal — the stuck-then-slip transition happened faster
            # than this segment's sample interval can resolve. This is a
            # censored (unmeasurable) observation, not evidence of a zero
            # stickband: counting it as S=0 would understate S for any
            # loop that cycles faster than the historian sample rate.
            # Skip it rather than let it masquerade as a measured zero.
            continue
        S_op = abs(op_segment[first_move] - op_segment[0])
        S_estimates.append(S_op)
        # Slip-jump: PV change at the first-move index minus expected
        if first_move < len(pv_segment) - 1:
            # Compare to a linear extrapolation of the OP excursion
            local_gain = np.polyfit(op[r1: r2], pv[r1: r2], 1)[0] if r2 > r1 + 2 else 1.0
            J_pv = abs(pv_segment[first_move])
            J_op = J_pv / max(abs(local_gain), 1e-3)
            J_estimates.append(min(J_op, S_op))

    S = float(np.median(S_estimates)) if S_estimates else None
    J = float(np.median(J_estimates)) if J_estimates else None
    return (round(S, 2) if S is not None else None,
            round(J, 2) if J is not None else None)


def stiction_consensus(pv, op, sp, metrics: LoopMetrics, config,
                       selection=None) -> StictionResult:
    """Run the enabled stiction methods and combine into a consensus.

    If `selection` is provided, only the methods flagged on (stic_heuristic,
    stic_horch, stic_yamashita, stic_bicoherence) are computed; the rest
    return 0 and contribute nothing to the weighted average. Disabled
    method weights are redistributed proportionally over the enabled ones.
    """
    res = StictionResult()
    use_h = selection is None or selection.stic_heuristic
    use_horch = selection is None or selection.stic_horch
    use_y = selection is None or selection.stic_yamashita
    use_b = selection is None or selection.stic_bicoherence

    if use_h:
        res.heuristic_score = stiction_heuristic(
            pv, op, sp, metrics.op_activity, metrics.pv_amplitude,
            metrics.iae_per_hour, config)
    if use_horch:
        res.horch_score = stiction_horch(pv, op)
    if use_y:
        res.yamashita_score, res.yamashita_shape = stiction_yamashita(pv, op)
    if use_b:
        res.bicoherence_score = stiction_bicoherence(pv)
    res.estimated_S, res.estimated_J = estimate_stiction_parameters(pv, op, config)

    # Build weight vector across the four methods, zeroing disabled ones
    raw_w = np.array([
        safe_float(config.get("STIC_W_HEURISTIC", 0.25)) if use_h else 0.0,
        safe_float(config.get("STIC_W_HORCH", 0.30)) if use_horch else 0.0,
        safe_float(config.get("STIC_W_YAMASHITA", 0.25)) if use_y else 0.0,
        safe_float(config.get("STIC_W_BICOH", 0.20)) if use_b else 0.0,
    ])
    if raw_w.sum() <= 0:
        # No methods enabled — caller should have caught this, but guard
        res.consensus_score = 0.0
        res.consensus_label = "Healthy"
        return res
    w = raw_w / raw_w.sum()
    s = np.array([res.heuristic_score, res.horch_score,
                  res.yamashita_score, res.bicoherence_score])
    res.consensus_score = round(float(np.dot(w, s)), 1)
    enabled_scores = s[raw_w > 0]
    res.methods_agreeing = int(np.sum(enabled_scores > 50))

    high = safe_float(config.get("STICT_CONF_HIGH", 70))
    med = safe_float(config.get("STICT_CONF_MED", 40))
    n_enabled = int((raw_w > 0).sum())
    # Need ≥ 2 methods agreeing for "Confirmed", but only if ≥2 are running.
    # If only 1 method is running (fall_back=1), Confirmed is unreachable.
    if res.consensus_score >= high and res.methods_agreeing >= min(2, n_enabled):
        res.consensus_label = "Confirmed" if n_enabled >= 2 else "Likely"
    elif res.consensus_score >= high:
        res.consensus_label = "Likely"
    elif res.consensus_score >= med:
        res.consensus_label = "Possible"
    else:
        res.consensus_label = "Healthy"
    return res
