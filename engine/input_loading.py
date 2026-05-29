"""
Input loading — all Excel readers and config-sheet parsers.
=============================================================

Layer 1, module 2. Reads the input file, detects PV/OP/SP loops, and
parses every configuration sheet:

  * `DIAGNOSTIC_CONFIG`   — numeric thresholds
  * `UNIT_MAPPING`        — loop-to-unit mapping
  * `MODE_MAPPING`        — plant-specific MODE values → canonical labels
  * `DIAGNOSTIC_SELECTION` — which diagnostics to enable
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .utils import logger, safe_float, DEFAULTS


def find_header_row(path: str, keyword: str = "TIMESTAMP", max_scan: int = 50) -> int:
    """Find the row containing the header keyword."""
    tmp = pd.read_excel(path, header=None, nrows=max_scan, sheet_name=0)
    for i in range(len(tmp)):
        row_vals = tmp.iloc[i].astype(str).str.strip().str.upper().values
        if keyword.upper() in row_vals:
            return i
    raise RuntimeError(f"'{keyword}' header not found in first {max_scan} rows.")


def load_clean_dataframe(path: str) -> pd.DataFrame:
    """Load and normalise the data sheet."""
    h = find_header_row(path, "TIMESTAMP")
    df = pd.read_excel(path, header=h, sheet_name=0)
    # Drop unit-row columns like "[PV]"
    df = df.loc[:, ~df.columns.astype(str).str.strip().str.startswith("[")]
    # Drop duplicate columns — keep first occurrence
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    # Normalise column names
    df.columns = (
        df.columns.astype(str).str.strip().str.upper()
        .str.replace(r"[\s\n\r]+", "_", regex=True).str.replace("-", "_", regex=False)
    )
    # Find timestamp
    ts_col = "TIMESTAMP"
    if ts_col not in df.columns:
        cands = [c for c in df.columns if "TIMESTAMP" in c]
        if cands:
            ts_col = cands[0]
        else:
            raise RuntimeError("Cannot find TIMESTAMP column.")

    # Convert TIMESTAMP. Handle Excel serial dates.
    if not pd.api.types.is_datetime64_any_dtype(df[ts_col]):
        # Try Excel serial first
        try:
            df[ts_col] = pd.to_datetime(df[ts_col], unit="D", origin="1899-12-30",
                                        errors="coerce")
        except Exception:
            df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        # If most are NaT, retry as plain datetime
        if df[ts_col].isna().mean() > 0.5:
            df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")

    # Convert numeric columns; preserve MODE columns as strings
    mode_cols = [c for c in df.columns if c.endswith("_MODE") or c == "MODE"]
    non_ts = [c for c in df.columns if c != ts_col and c not in mode_cols]
    df[non_ts] = df[non_ts].apply(pd.to_numeric, errors="coerce")
    # Keep MODE values in their raw form (just strip/uppercase whitespace).
    # Translation to canonical AUTO/CAS/RCAS/MAN is done later via the
    # MODE_MAPPING sheet so users with non-standard mode codes (numeric,
    # single-letter, custom strings) work correctly.
    for mc in mode_cols:
        df[mc] = df[mc].astype(str).str.strip()
    df = df.dropna(subset=[ts_col]).reset_index(drop=True)
    return df


# ─── Loop detection ───────────────────────────────────────────────────
def detect_loops(df: pd.DataFrame) -> dict:
    """Find {LOOPNAME: {'PV': col, 'OP': col, 'SP': col, 'MODE': col?}} triplets."""
    loops = {}
    for col in df.columns:
        c = col.upper()
        for sig in ("PV", "OP", "SP", "MODE"):
            if c.endswith("_" + sig):
                base = c[: -(len(sig) + 1)]
                if base:
                    loops.setdefault(base, {})[sig] = col
                break
    return {b: cols for b, cols in loops.items()
            if {"PV", "OP", "SP"}.issubset(cols.keys())}


# ─── Config loading ───────────────────────────────────────────────────
def load_detection_exclusions(path: str) -> dict:
    """
    Load optional DETECTION_EXCLUSIONS sheet.
    Returns {problem_id: set_of_loop_names}, e.g.
    {'stiction': {'FIC-101', 'TIC-202'}, 'aggressive_tuning': {'FIC-101'}}
    """
    excl = {}
    try:
        df = pd.read_excel(path, sheet_name="DETECTION_EXCLUSIONS")
        df = df.dropna(subset=["Problem", "Loop"])
        for _, row in df.iterrows():
            pid  = str(row["Problem"]).strip().lower()
            loop = str(row["Loop"]).strip()
            excl.setdefault(pid, set()).add(loop)
    except Exception:
        pass  # sheet missing or empty — no exclusions
    return excl


def load_config(path: str) -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg_df = pd.read_excel(path, sheet_name="DIAGNOSTIC_CONFIG")
        cfg_df = cfg_df.dropna(subset=["Parameter", "Value"])
        for _, row in cfg_df.iterrows():
            k = str(row["Parameter"]).strip()
            v = pd.to_numeric(row["Value"], errors="coerce")
            if pd.notna(v):
                cfg[k] = float(v)
        logger.info("Diagnostic config loaded from Excel")
    except Exception as e:
        logger.warning(f"Using default diagnostic config ({e})")
    return cfg


def load_unit_mapping(path: str) -> dict:
    """
    Load optional UNIT_MAPPING sheet that groups loops by plant unit.

    Expected sheet layout (two columns):
        Tag         Unit
        FIC-101     Deethanizer
        TIC-101     Deethanizer
        FIC-102     Deprop
        ...

    Returns: {normalised_loop_name: unit_name}.  Loops not listed are
    treated as belonging to unit 'Unknown'.

    The sheet is OPTIONAL.  Without it, all loops are placed in unit
    'Unknown' and propagation analysis treats every pair as same-unit.
    """
    try:
        mp = pd.read_excel(path, sheet_name="UNIT_MAPPING")
        mp.columns = mp.columns.str.strip()
        # Accept any case for column headers
        cols_upper = {c.upper(): c for c in mp.columns}
        tag_col = cols_upper.get("TAG") or cols_upper.get("TAGS")
        unit_col = cols_upper.get("UNIT") or cols_upper.get("UNITS")
        if not tag_col or not unit_col:
            logger.info("UNIT_MAPPING sheet missing 'Tag'/'Unit' columns; ignoring")
            return {}
        mp = mp[[tag_col, unit_col]].dropna()
        mapping = {}
        for _, row in mp.iterrows():
            tag = str(row[tag_col]).strip().upper().replace("-", "_")
            unit = str(row[unit_col]).strip()
            if not tag or not unit:
                continue
            # Strip _PV/_OP/_SP/_MODE suffixes if user listed them
            for suf in ("_PV", "_OP", "_SP", "_MODE"):
                if tag.endswith(suf):
                    tag = tag[: -len(suf)]
                    break
            mapping[tag] = unit
        if mapping:
            n_units = len(set(mapping.values()))
            logger.info(f"Unit mapping loaded: {len(mapping)} loops across {n_units} units")
        return mapping
    except Exception as e:
        logger.info(f"No UNIT_MAPPING sheet found ({e}); all loops treated as unit 'Unknown'")
        return {}


# ═══════════════════════════════════════════════════════════════════════
# MODE MAPPING — translate plant-specific MODE values to canonical categories
# ═══════════════════════════════════════════════════════════════════════

# Canonical categories. AUTO/CAS/RCAS are all "analyzable" (loop being
# controlled). MAN means operator override — exclude from analysis.
_MODE_ANALYZABLE = {"AUTO", "CAS", "RCAS"}

# Built-in fallback used when no MODE_MAPPING sheet is provided.
_MODE_DEFAULT_MAPPING = {
    "AUTO": "AUTO", "A": "AUTO", "1": "AUTO", "AUTOMATIC": "AUTO",
    "CAS": "CAS", "CASCADE": "CAS", "C": "CAS", "2": "CAS",
    "RCAS": "RCAS", "REMOTE": "RCAS", "R": "RCAS", "3": "RCAS",
    "MAN": "MAN", "MANUAL": "MAN", "M": "MAN", "0": "MAN",
}


def load_mode_mapping(path: str) -> dict:
    """Load optional MODE_MAPPING sheet that translates plant-specific MODE
    values (numbers, letters, words) into canonical AUTO / CAS / RCAS / MAN.

    Sheet layout (two columns, multiple rows):
        Category   Value
        AUTO       AUTO
        AUTO       A
        AUTO       1
        AUTO       Automatic
        CAS        CAS
        CAS        C
        ...
        MAN        MAN
        MAN        0

    Comparison is case-insensitive and numeric-vs-string-safe (1 and "1"
    both match). Returns {raw_value_uppercase_string: canonical_category}.

    If the sheet is missing or empty, returns the built-in default
    mapping covering common conventions.

    AUTO / CAS / RCAS are considered analyzable; MAN excludes the sample.
    """
    try:
        mp = pd.read_excel(path, sheet_name="MODE_MAPPING")
        mp.columns = mp.columns.str.strip()
        cols_upper = {c.upper(): c for c in mp.columns}
        cat_col = cols_upper.get("CATEGORY") or cols_upper.get("CANONICAL")
        val_col = cols_upper.get("VALUE") or cols_upper.get("VALUES") or cols_upper.get("RAW")
        if not cat_col or not val_col:
            logger.info("MODE_MAPPING sheet missing 'Category'/'Value' columns; "
                        "using built-in defaults")
            return dict(_MODE_DEFAULT_MAPPING)

        mapping = {}
        for _, row in mp.iterrows():
            cat = row.get(cat_col)
            val = row.get(val_col)
            if pd.isna(cat) or pd.isna(val):
                continue
            cat_norm = str(cat).strip().upper()
            if cat_norm not in {"AUTO", "CAS", "RCAS", "MAN"}:
                logger.warning(f"MODE_MAPPING: unknown category '{cat}' — ignored "
                               "(must be AUTO, CAS, RCAS, or MAN)")
                continue
            # Normalise the user's mode value: strip whitespace, uppercase,
            # and strip trailing .0 from numeric values (Excel auto-converts
            # integer modes like 1 to 1.0 when the column is mixed)
            val_norm = str(val).strip().upper()
            if val_norm.endswith(".0"):
                val_norm = val_norm[:-2]
            if val_norm:
                mapping[val_norm] = cat_norm

        if not mapping:
            logger.info("MODE_MAPPING sheet empty; using built-in defaults")
            return dict(_MODE_DEFAULT_MAPPING)

        n_per_cat = {}
        for v, c in mapping.items():
            n_per_cat[c] = n_per_cat.get(c, 0) + 1
        cat_summary = ", ".join(f"{c}={n}" for c, n in n_per_cat.items())
        logger.info(f"MODE_MAPPING loaded: {len(mapping)} value(s) ({cat_summary})")
        return mapping
    except Exception as e:
        logger.info(f"No MODE_MAPPING sheet found ({e}); using built-in defaults")
        return dict(_MODE_DEFAULT_MAPPING)


# Module-level set so warnings about unrecognised mode values fire only once
# per distinct value across the whole run, not once per loop or per sample.
_unrecognised_modes_logged = set()


def _reset_mode_warnings():
    """Call at the start of each run."""
    _unrecognised_modes_logged.clear()


def _classify_mode_value(raw, mode_mapping: dict) -> str:
    """Translate one raw MODE cell value to AUTO/CAS/RCAS/MAN.
    Unrecognised values are treated as MAN with a one-time warning per value.
    """
    if pd.isna(raw):
        return "MAN"   # null → safest assumption (exclude)
    s = str(raw).strip().upper()
    if s.endswith(".0"):
        s = s[:-2]
    if not s or s == "NAN":
        return "MAN"
    cat = mode_mapping.get(s)
    if cat is not None:
        return cat
    # Unknown value — log once
    if s not in _unrecognised_modes_logged:
        _unrecognised_modes_logged.add(s)
        logger.warning(
            f"Unrecognised MODE value '{s}' — treating as MAN (excluded from "
            "analysis). Add to MODE_MAPPING sheet if this should be analyzable."
        )
    return "MAN"


# ═══════════════════════════════════════════════════════════════════════
# DIAGNOSTIC SELECTION — user opts out of specific diagnoses
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DiagnosticSelection:
    """User's choice of which diagnostics to run.

    Hierarchy:
      Parent diagnoses (master switch — disables all children when off):
        - stiction_detection
        - aggressive_tuning
        - sluggish_tuning
        - external_oscillation
        - cross_loop_propagation

      Sub-methods (only meaningful if their parent is enabled):
        Stiction:        heuristic, horch, yamashita, bicoherence, fall_back
        Aggressive/Ext:  harris, hagglund (shared globally)
        Sluggish:        harris (shared)
        Propagation:     cross_correlation, granger, coherence

    Resolution: option (b) — Harris and Hägglund are global. If the user
    sets them to 1 anywhere they appear, they run once and the result is
    shared by every parent diagnosis that uses them.

    Auto-disable rules (logged when triggered):
      • Parent disabled → all children effectively off.
      • Stiction detection requires ≥2 of (heuristic, horch, yamashita,
        bicoherence) unless fall_back=1.
      • Aggressive tuning requires harris=1 AND hagglund=1.
      • Sluggish tuning requires harris=1.
      • External oscillation requires harris=1 AND hagglund=1.
      • Cross-loop propagation requires ≥1 of (cross-correlation,
        granger, coherence).
    """
    # Parents (master switches)
    stiction_detection: bool = True
    aggressive_tuning: bool = True
    sluggish_tuning: bool = True
    external_oscillation: bool = True
    cross_loop_propagation: bool = True

    # Stiction sub-methods
    stic_heuristic: bool = True
    stic_horch: bool = True
    stic_yamashita: bool = True
    stic_bicoherence: bool = True
    stic_fall_back: bool = True

    # Performance metrics (shared globally)
    harris_index: bool = True
    hagglund_oscillation: bool = True

    # Propagation sub-methods
    prop_cross_correlation: bool = True
    prop_granger: bool = True
    prop_coherence: bool = True

    # Audit trail of auto-disable decisions
    auto_disable_log: list = field(default_factory=list)

    def resolve(self):
        """Apply parent-disables-children rule and dependency checks.
        Mutates self in place; appends explanations to auto_disable_log.
        Call this exactly once after loading from the user's sheet.
        """
        log = self.auto_disable_log

        # ── 1. Parent off → all children off
        if not self.stiction_detection:
            for k in ("stic_heuristic", "stic_horch", "stic_yamashita",
                      "stic_bicoherence", "stic_fall_back"):
                if getattr(self, k):
                    setattr(self, k, False)
                    log.append(f"{k} disabled because parent 'Stiction detection' is off")
        if not self.cross_loop_propagation:
            for k in ("prop_cross_correlation", "prop_granger", "prop_coherence"):
                if getattr(self, k):
                    setattr(self, k, False)
                    log.append(f"{k} disabled because parent 'Cross-loop propagation' is off")

        # ── 2. Stiction needs ≥2 methods (or fall_back enabled with ≥1 method)
        if self.stiction_detection:
            n_methods = sum([self.stic_heuristic, self.stic_horch,
                             self.stic_yamashita, self.stic_bicoherence])
            if n_methods == 0:
                self.stiction_detection = False
                log.append("Stiction detection auto-disabled: no methods enabled")
            elif n_methods == 1 and not self.stic_fall_back:
                self.stiction_detection = False
                log.append("Stiction detection auto-disabled: only 1 method enabled "
                           "and 'fall back' is off (consensus needs ≥2 methods)")
            elif n_methods == 1 and self.stic_fall_back:
                log.append("Stiction detection running with 1 method only "
                           "(fall_back=1) — consensus confidence will be limited")

        # ── 3. Aggressive tuning needs Harris AND Hägglund
        if self.aggressive_tuning and not (self.harris_index and self.hagglund_oscillation):
            self.aggressive_tuning = False
            missing = []
            if not self.harris_index: missing.append("Harris Index")
            if not self.hagglund_oscillation: missing.append("Hägglund oscillation")
            log.append(f"Aggressive tuning auto-disabled: requires {' AND '.join(missing)}")

        # ── 4. Sluggish tuning needs Harris
        if self.sluggish_tuning and not self.harris_index:
            self.sluggish_tuning = False
            log.append("Sluggish tuning auto-disabled: requires Harris Index")

        # ── 5. External oscillation needs Harris AND Hägglund
        if self.external_oscillation and not (self.harris_index and self.hagglund_oscillation):
            self.external_oscillation = False
            missing = []
            if not self.harris_index: missing.append("Harris Index")
            if not self.hagglund_oscillation: missing.append("Hägglund oscillation")
            log.append(f"External oscillation auto-disabled: requires {' AND '.join(missing)}")

        # ── 6. Propagation needs ≥1 method
        if self.cross_loop_propagation:
            n_prop = sum([self.prop_cross_correlation, self.prop_granger,
                          self.prop_coherence])
            if n_prop == 0:
                self.cross_loop_propagation = False
                log.append("Cross-loop propagation auto-disabled: no methods enabled")


# Map from user-facing labels (case-insensitive) to internal field names.
# Multiple labels can map to the same field (e.g. Harris appears under
# 3 parent diagnoses but is a single global flag — option (b)).
_DIAG_LABEL_MAP = {
    # parents
    "stiction detection": "stiction_detection",
    "aggressive tuning": "aggressive_tuning",
    "sluggish tuning": "sluggish_tuning",
    "external oscillation": "external_oscillation",
    "cross-loop propagation": "cross_loop_propagation",
    "cross loop propagation": "cross_loop_propagation",
    "propagation": "cross_loop_propagation",
    # stiction children
    "heuristic method": "stic_heuristic",
    "heuristic": "stic_heuristic",
    "horch cross-correlation": "stic_horch",
    "horch cross correlation": "stic_horch",
    "horch": "stic_horch",
    "yamashita shape": "stic_yamashita",
    "yamashita": "stic_yamashita",
    "bicoherence": "stic_bicoherence",
    "fall back to other indicators if methods disagree": "stic_fall_back",
    "fall back": "stic_fall_back",
    "fall back to other indicators": "stic_fall_back",
    # performance metrics
    "harris index": "harris_index",
    "harris": "harris_index",
    "hagglund oscillation": "hagglund_oscillation",
    "hägglund oscillation": "hagglund_oscillation",
    "hagglund": "hagglund_oscillation",
    "hägglund": "hagglund_oscillation",
    # propagation children
    "cross-correlation": "prop_cross_correlation",
    "cross correlation": "prop_cross_correlation",
    "granger causality": "prop_granger",
    "granger": "prop_granger",
    "spectral coherence": "prop_coherence",
    "coherence": "prop_coherence",
}


def load_diagnostic_selection(path: str) -> DiagnosticSelection:
    """Load optional DIAGNOSTIC_SELECTION sheet.

    Sheet format (two columns: Diagnostic, Enabled):
        Stiction detection                   1
            Heuristic method                 1
            Horch cross-correlation          1
            Yamashita shape                  1
            Bicoherence                      1
            Fall back to other indicators    1
        Aggressive tuning                    1
            Harris Index                     1
            Hagglund oscillation             1
        ...

    Indentation, hyphens, and accents are ignored. Any value evaluating
    to False (0, FALSE, no, off, blank) means disabled; everything else
    means enabled. Missing rows default to enabled.

    Multiple occurrences of the same diagnostic (e.g. Harris appears under
    three parents) are resolved with OR — if ANY occurrence is enabled,
    the diagnostic runs once and is shared. This is option (b).

    Returns a DiagnosticSelection object with .resolve() already applied.
    """
    sel = DiagnosticSelection()
    try:
        df = pd.read_excel(path, sheet_name="DIAGNOSTIC_SELECTION")
        df.columns = df.columns.str.strip()
        cols_upper = {c.upper(): c for c in df.columns}
        diag_col = (cols_upper.get("DIAGNOSTIC") or cols_upper.get("DIAGNOSIS")
                    or cols_upper.get("NAME") or df.columns[0])
        en_col = (cols_upper.get("ENABLED") or cols_upper.get("ENABLE")
                  or cols_upper.get("ON") or df.columns[1])
    except Exception as e:
        logger.info(f"No DIAGNOSTIC_SELECTION sheet found ({e}); all diagnostics enabled")
        sel.resolve()
        return sel

    # Track per-field values seen; we OR them at the end (option b)
    seen = {}
    for _, row in df.iterrows():
        raw = row.get(diag_col)
        if pd.isna(raw):
            continue
        label = str(raw).strip().lstrip("-•·>").strip().lower()
        # strip leading whitespace already, also collapse internal whitespace
        label = " ".join(label.split())
        if not label or label.startswith("---"):
            continue
        field_name = _DIAG_LABEL_MAP.get(label)
        if field_name is None:
            logger.warning(f"DIAGNOSTIC_SELECTION row '{raw}' not recognised — ignored")
            continue
        # Parse the enabled value
        v = row.get(en_col)
        if pd.isna(v):
            enabled = True   # blank = enabled (default)
        elif isinstance(v, (int, float)):
            enabled = bool(int(v)) if np.isfinite(v) else True
        else:
            s = str(v).strip().lower()
            enabled = s not in ("0", "no", "false", "off", "n", "")
        # OR with anything we've seen for this field
        seen[field_name] = seen.get(field_name, False) or enabled

    # Apply: only override defaults for fields the user actually listed
    for field_name, value in seen.items():
        setattr(sel, field_name, value)

    n_disabled = sum(1 for f in [
        sel.stiction_detection, sel.aggressive_tuning, sel.sluggish_tuning,
        sel.external_oscillation, sel.cross_loop_propagation,
        sel.harris_index, sel.hagglund_oscillation,
        sel.stic_heuristic, sel.stic_horch, sel.stic_yamashita, sel.stic_bicoherence,
        sel.prop_cross_correlation, sel.prop_granger, sel.prop_coherence,
    ] if not f)
    if n_disabled:
        logger.info(f"Diagnostic selection loaded: {n_disabled} item(s) disabled by user")
    else:
        logger.info("Diagnostic selection loaded: all items enabled")

    sel.resolve()
    for msg in sel.auto_disable_log:
        logger.warning(f"Auto-disable: {msg}")
    return sel
