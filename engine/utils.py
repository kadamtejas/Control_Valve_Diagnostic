"""
Engine utilities — logger, DEFAULTS, and small math safety helpers.
=====================================================================

Imported by every other engine module. Owns:

  * `logger`     — the module-level logging.Logger used throughout v2.
  * `DEFAULTS`   — fallback values for every numeric threshold.
  * `safe_float` / `safe_pos` — defensive number conversion.
  * `setup_logging` — file + console logger configuration.
"""

import logging
import os
import warnings

import numpy as np

warnings.filterwarnings("ignore")

# ─── Logging ──────────────────────────────────────────────────────────
logger = logging.getLogger("valve_diag")


def setup_logging(log_path: str, verbose: bool = True):
    """Configure the file + console handlers exactly once."""
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if verbose:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)


# ─── Defaults and helpers ─────────────────────────────────────────────
DEFAULTS = {
    # thresholds (calibrated for OP%/PV% in 0-100 engineering units;
    # these scale-dependent values can be overridden via DIAGNOSTIC_CONFIG)
    "AMP_THRESHOLD": 15.0,
    "OP_ACTIVITY_THRESHOLD": 1.5,
    "IAE_PER_HOUR_THRESHOLD": 200.0,
    "STICT_CONF_HIGH": 70.0,
    "STICT_CONF_MED": 40.0,
    "PROP_CONF_MIN": 50.0,
    "PROP_CONF_STRONG": 70.0,
    "SERVICE_FACTOR_MIN_PCT": 70.0,
    "SS_DETECTION_WINDOW": 30,
    "SS_STD_THRESHOLD": 0.5,
    "FROZEN_SAMPLES_MIN": 10,
    "QUANTISATION_UNIQUE_VALS_MAX": 20,
    "COMPRESSION_FLAT_FRACTION_MAX": 0.30,
    "OSCILLATION_REGULARITY_MIN": 0.6,
    "STICTION_S_MIN_PCT": 0.5,
    "HARRIS_INDEX_THRESHOLD": 0.3,
    # consensus weights for stiction
    "STIC_W_HEURISTIC": 0.20,
    "STIC_W_HORCH": 0.30,
    "STIC_W_YAMASHITA": 0.30,
    "STIC_W_BICOH": 0.20,
    # capability gates (max sample interval in seconds for each diagnostic)
    "MAX_DT_FOR_STICTION_SEC": 300.0,    # 5 min
    "MAX_DT_FOR_OSCILLATION_SEC": 300.0,  # 5 min
    "MAX_DT_FOR_HARRIS_SEC": 300.0,       # 5 min
    "MAX_DT_FOR_PROPAGATION_SEC": 600.0,  # 10 min
    # plot settings
    "PLOT_WIDTH": 11.0,
    "PLOT_HEIGHT": 7.0,
    # propagation settings
    "MAX_LAG_SAMPLES": 50,
    "GRANGER_MAX_LAG": 5,
    "GRANGER_P_THRESHOLD": 0.05,
    "CROSS_UNIT_DOWNWEIGHT": 0.5,
    # plant KPIs
    "TOP_N_WORST_LOOPS": 10,
    "PLANT_HEALTH_GOOD_THRESHOLD": 75.0,
    "PLANT_HEALTH_POOR_THRESHOLD": 50.0,
}


def safe_float(v, fallback=0.0):
    try:
        x = float(v)
        return x if np.isfinite(x) else fallback
    except Exception:
        return fallback


def safe_pos(v, fallback=1.0):
    """Like safe_float but ensures result is > 0."""
    x = safe_float(v, fallback)
    return x if x > 0 else fallback
