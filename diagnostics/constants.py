"""
Constants used across the v3 wrapper.
========================================

All thresholds, severity labels, sentinel values, and parameter ranges live
here so they can be reviewed in one place.
"""

V3_VERSION = "3.0.0"

# ──────────────────────────────────────────────────────────────────────
# Severity levels for health-check items
# ──────────────────────────────────────────────────────────────────────
PROBLEM = "PROBLEM"   # blocks the run
WARNING = "WARNING"   # tool continues
INFO = "INFO"         # purely informational
PASSED = "PASSED"     # check succeeded

# ──────────────────────────────────────────────────────────────────────
# Hard sanity bounds for auto-calibration (Layer 3 safeguard).
# Each calibrated value is clamped between these floors and ceilings.
# ──────────────────────────────────────────────────────────────────────
CALIB_BOUNDS = {
    "AMP_THRESHOLD":              (1.0,    50.0),
    "OP_ACTIVITY_THRESHOLD":      (0.1,    20.0),
    "IAE_PER_HOUR_THRESHOLD":     (20.0,  2000.0),
    "SS_STD_THRESHOLD":           (0.05,    5.0),
    "SS_DETECTION_WINDOW":        (10,    300),
    "FROZEN_SAMPLES_MIN":         (5,     200),
}

# Parameters that should NEVER be auto-calibrated (industry conventions
# or physical thresholds — see Bucket 4 in the design doc).
NEVER_AUTO_CALIBRATE = {
    "STICT_CONF_HIGH", "STICT_CONF_MED",
    "PROP_CONF_MIN", "PROP_CONF_STRONG",
    "SERVICE_FACTOR_MIN_PCT",
    "QUANTISATION_UNIQUE_VALS_MAX",
    "COMPRESSION_FLAT_FRACTION_MAX",
    "OSCILLATION_REGULARITY_MIN",
    "STICTION_S_MIN_PCT",
    "HARRIS_INDEX_THRESHOLD",
}

# ──────────────────────────────────────────────────────────────────────
# Sentinel-value catalogue (Stage 4 / repair module).
# These are not real measurements — they're "no value" markers from
# legacy DCS and historian systems.
# ──────────────────────────────────────────────────────────────────────
NUMERIC_SENTINELS = (-9999, -999, 99999, -32767)

# Quality-flag text values that historian exports sometimes leak through.
QUALITY_FLAGS = {
    "bad", "bad quality", "i/o timeout", "comm fail", "comm error",
    "configure", "shutdown", "calc off", "no data", "intf shut",
    "not connect", "scan off", "pt created", "calc failed",
}

# Excel error markers
EXCEL_ERRORS = {"#N/A", "#NULL!", "#DIV/0!", "#REF!", "#VALUE!", "#NAME?", "#NUM!"}

# ──────────────────────────────────────────────────────────────────────
# Sensible ranges for each config parameter (used for warning, not blocking).
# Tuple = (min, max, default).
# ──────────────────────────────────────────────────────────────────────
CONFIG_RANGES = {
    "AMP_THRESHOLD":              (1.0,    50.0,  15.0),
    "OP_ACTIVITY_THRESHOLD":      (0.1,    20.0,   1.5),
    "IAE_PER_HOUR_THRESHOLD":     (20.0,  2000.0, 200.0),
    "STICT_CONF_HIGH":            (40.0,    95.0, 70.0),
    "STICT_CONF_MED":             (20.0,    70.0, 40.0),
    "PROP_CONF_MIN":              (20.0,    80.0, 50.0),
    "PROP_CONF_STRONG":           (50.0,    95.0, 70.0),
    "SERVICE_FACTOR_MIN_PCT":     (10.0,    99.0, 70.0),
    "SS_DETECTION_WINDOW":        (5,      500,   30),
    "SS_STD_THRESHOLD":           (0.05,    5.0,   0.5),
    "FROZEN_SAMPLES_MIN":         (3,      500,   10),
    "QUANTISATION_UNIQUE_VALS_MAX":(2,     500,   20),
    "COMPRESSION_FLAT_FRACTION_MAX":(0.05, 0.95,   0.30),
    "OSCILLATION_REGULARITY_MIN": (0.2,    0.95,  0.6),
    "STICTION_S_MIN_PCT":         (0.05,   10.0,  0.5),
    "HARRIS_INDEX_THRESHOLD":     (0.05,   0.95,  0.3),
}
