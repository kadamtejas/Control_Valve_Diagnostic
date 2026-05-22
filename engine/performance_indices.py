"""
Performance indices — Harris index and Hägglund regularity.
=============================================================

Layer 2, module 2. Industry-standard performance metrics:

  * Harris index — minimum-variance benchmark; how close is the loop
                   to ideal control?
  * Hägglund    — oscillation regularity; is there a sustained,
                   regular oscillation?
"""

import numpy as np
import pandas as pd

from .utils import safe_float, safe_pos
from .loop_metrics import estimate_dead_time_samples


def harris_index(pv: np.ndarray, sp: np.ndarray, op: np.ndarray,
                 dead_time_samples: int = None, ar_order: int = 30) -> float:
    """
    Harris (1989) Minimum Variance Index.
    HI = sigma_mv^2 / sigma_actual^2 ∈ [0, 1]
      1.0 = ideal (already at minimum variance)
      0.0 = no control / poor control

    Implementation: fit AR(p) to PV-SP error; the b-step-ahead prediction
    error variance gives sigma_mv^2.
    """
    err = pv - sp
    err = err[np.isfinite(err)]
    if len(err) < 100 or np.std(err) < 1e-9:
        return float("nan")
    if dead_time_samples is None:
        dead_time_samples = estimate_dead_time_samples(op, pv)
    b = max(int(dead_time_samples), 1)
    p = max(ar_order, b + 5)
    p = min(p, len(err) // 4)

    # Fit AR(p) using Yule-Walker
    e = err - np.mean(err)
    n = len(e)
    # Autocovariance
    r = np.array([np.dot(e[: n - k], e[k:]) / n for k in range(p + 1)])
    R = np.array([[r[abs(i - j)] for j in range(p)] for i in range(p)])
    try:
        phi = np.linalg.solve(R + np.eye(p) * 1e-9, r[1:])
    except np.linalg.LinAlgError:
        return float("nan")
    sigma_e2 = r[0] - np.dot(phi, r[1:])
    if sigma_e2 <= 0:
        return float("nan")

    # Impulse response of 1/A(q) — first b coefficients
    h = np.zeros(b + 1)
    h[0] = 1.0
    for k in range(1, b + 1):
        h[k] = sum(phi[j] * h[k - 1 - j] for j in range(min(k, p)))
    sigma_mv2 = sigma_e2 * np.sum(h[:b] ** 2) if b >= 1 else sigma_e2

    actual_var = float(np.var(err))
    if actual_var < 1e-12:
        return float("nan")
    hi = float(sigma_mv2 / actual_var)
    return float(np.clip(hi, 0.0, 1.0))


# ─── Hägglund oscillation regularity ───────────────────────────────────
def haglund_oscillation_index(err: np.ndarray) -> tuple:
    """
    Returns (regularity, dominant_period_samples).
    Regularity ∈ [0,1]: 1 means perfectly periodic, 0 means random.
    Hägglund's idea: zero crossings of the (filtered) error should be evenly
    spaced if there is an oscillation.
    """
    err = np.asarray(err, dtype=float)
    err = err[np.isfinite(err)]
    if len(err) < 30:
        return float("nan"), 0
    e = err - np.mean(err)
    # Mild low-pass to ignore noise
    if len(e) > 11:
        e = pd.Series(e).rolling(5, center=True, min_periods=1).mean().values
    sign = np.sign(e)
    # Avoid 0 sign issues
    sign[sign == 0] = 1
    crossings = np.where(np.diff(sign) != 0)[0]
    if len(crossings) < 4:
        return 0.0, 0
    intervals = np.diff(crossings)
    if len(intervals) < 3:
        return 0.0, 0
    mean_int = np.mean(intervals)
    std_int = np.std(intervals)
    if mean_int < 1:
        return 0.0, 0
    regularity = float(1.0 / (1.0 + std_int / mean_int))
    period = int(2 * mean_int)  # full period = two zero-crossing intervals
    return round(regularity, 3), period
