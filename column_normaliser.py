"""
column_normaliser.py
====================
Normalises control-loop column names from any incoming format into the
standard format the diagnostic engine expects:

    LOOPTAG_PV  |  LOOPTAG_OP  |  LOOPTAG_SP  |  LOOPTAG_MODE

Three input formats are handled automatically:

  Format 1 — underscore separator   : LOOPTAG_PV, LOOPTAG_OP, LOOPTAG_SP, LOOPTAG_MODE
  Format 2 — dot separator          : LOOPTAG.PV, LOOPTAG.OP, LOOPTAG.SP, LOOPTAG.MODE
  Format 3 — bare tag (no PV suffix): LOOPTAG, LOOPTAGOP, LOOPTAGSP  (MODE absent → AUTO)

Rules applied:
  - Detection is case-insensitive (pv / PV / Pv all recognised).
  - If MODE column is missing for a loop, it is created and filled with "AUTO".
  - The TIMESTAMP column is never touched.
  - All other columns (non-loop columns) are passed through unchanged.
  - The original DataFrame is never modified; a new one is returned.

Usage
-----
    from column_normaliser import normalise_columns

    df_raw = pd.read_excel("my_plant_data.xlsx", sheet_name="Sheet1")
    df_norm, report = normalise_columns(df_raw)
    # df_norm is ready for the diagnostic engine
    # report is a list of human-readable strings describing what was done
"""

import re
import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalise_columns(df: pd.DataFrame, auto_mode_value: str = "AUTO"):
    """
    Detect the column naming format and return a normalised copy of df.

    Parameters
    ----------
    df              : raw input DataFrame (columns not yet standardised)
    auto_mode_value : string to fill into MODE columns that were missing
                      (default "AUTO" — matches the tool's MODE_MAPPING)

    Returns
    -------
    df_norm  : pd.DataFrame  — normalised copy, ready for the engine
    report   : list[str]     — human-readable log of every change made
    """
    report = []
    cols = list(df.columns)

    fmt = _detect_format(cols)
    report.append(f"Detected column format: {fmt}")

    if fmt == "FORMAT_1_UNDERSCORE":
        df_norm, fmt_report = _normalise_format1(df, sep="_")
    elif fmt == "FORMAT_2_DOT":
        df_norm, fmt_report = _normalise_format1(df, sep=".")
    elif fmt == "FORMAT_3_BARE":
        df_norm, fmt_report = _normalise_format3(df)
    else:
        # Already standard or unrecognised — return as-is
        report.append("No renaming needed — columns already in standard format.")
        return df.copy(), report

    report.extend(fmt_report)

    # Fill missing MODE columns with auto_mode_value
    mode_report = _fill_missing_mode(df_norm, auto_mode_value)
    report.extend(mode_report)

    # Normalise MODE column name capitalisation (_mode / _Mode → _MODE)
    cap_report = _normalise_mode_case(df_norm)
    report.extend(cap_report)

    return df_norm, report


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_SIGNAL_SUFFIXES = ("PV", "MV", "OP", "SP", "MODE")

# Map non-standard suffixes to the canonical name the engine expects
_SUFFIX_ALIAS = {"MV": "PV"}


def _detect_format(cols):
    """
    Return one of:
      FORMAT_1_UNDERSCORE  — columns like  LOOPTAG_PV
      FORMAT_2_DOT         — columns like  LOOPTAG.PV
      FORMAT_3_BARE        — columns like  LOOPTAG, LOOPTAGOP, LOOPTAGSP
      UNKNOWN
    """
    upper_cols = [c.upper() for c in cols]

    underscore_hits = sum(
        1 for c in upper_cols
        if any(c.endswith(f"_{s}") for s in _SIGNAL_SUFFIXES)
    )
    dot_hits = sum(
        1 for c in upper_cols
        if any(c.endswith(f".{s}") for s in _SIGNAL_SUFFIXES)
    )
    # Format 3: OP or SP appended with no separator
    bare_op_hits = sum(
        1 for c in upper_cols
        if c.endswith("OP") and not c.endswith("_OP") and not c.endswith(".OP")
    )
    bare_sp_hits = sum(
        1 for c in upper_cols
        if c.endswith("SP") and not c.endswith("_SP") and not c.endswith(".SP")
    )

    if underscore_hits >= dot_hits and underscore_hits > 0:
        return "FORMAT_1_UNDERSCORE"
    if dot_hits > 0:
        return "FORMAT_2_DOT"
    if bare_op_hits > 0 or bare_sp_hits > 0:
        return "FORMAT_3_BARE"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Format 1 & 2 normaliser  (separator is _ or .)
# ---------------------------------------------------------------------------

def _normalise_format1(df, sep):
    """
    Rename LOOPTAG{sep}pv  →  LOOPTAG_PV  (uppercase signal suffix).
    Works for both underscore and dot separators.
    """
    rename_map = {}
    report = []
    escaped = re.escape(sep)

    for col in df.columns:
        # Match anything ending with <sep><signal> (case-insensitive)
        m = re.match(
            rf"^(.+){escaped}(PV|MV|OP|SP|MODE)$",
            col,
            flags=re.IGNORECASE,
        )
        if m:
            tag, signal = m.group(1), m.group(2).upper()
            signal = _SUFFIX_ALIAS.get(signal, signal)  # MV → PV
            new_name = f"{tag}_{signal}"
            if new_name != col:
                rename_map[col] = new_name
                report.append(f"  Renamed: {col!r}  →  {new_name!r}")

    df_norm = df.rename(columns=rename_map)
    if not rename_map:
        report.append("  No column renames needed.")
    return df_norm, report


# ---------------------------------------------------------------------------
# Format 3 normaliser  (bare tag = PV, OP/SP appended without separator)
# ---------------------------------------------------------------------------

def _normalise_format3(df):
    """
    Infer PV from bare tag name when OP and/or SP counterparts exist.

    Rule:
      If LOOPTAG+OP  exists in columns  →  LOOPTAG is the PV column
      (SP alone also accepted as confirmation, but OP is the primary signal)

    Each detected loop is renamed to:
      LOOPTAG        →  LOOPTAG_PV
      LOOPTAGOP      →  LOOPTAG_OP
      LOOPTAGSP      →  LOOPTAG_SP
      LOOPTAGMODE    →  LOOPTAG_MODE   (if present)
    """
    cols_upper = {c.upper(): c for c in df.columns}  # upper → original
    rename_map = {}
    report = []
    processed_tags = set()

    for col_upper, col_orig in cols_upper.items():
        if col_upper == "TIMESTAMP":
            continue

        # Try stripping OP / SP / MODE to find the base tag
        for suffix in ("OP", "SP", "MODE"):
            if col_upper.endswith(suffix) and not col_upper.endswith(f"_{suffix}") and not col_upper.endswith(f".{suffix}"):
                base_upper = col_upper[: -len(suffix)]
                if base_upper in processed_tags:
                    break
                if base_upper in cols_upper:
                    # Bare base tag exists → it's the PV
                    tag_orig = cols_upper[base_upper]

                    # Collect all signals for this tag
                    signals_found = {"PV": tag_orig}
                    for sig in ("OP", "SP", "MODE"):
                        candidate = base_upper + sig
                        if candidate in cols_upper:
                            signals_found[sig] = cols_upper[candidate]

                    # Only treat as a proper loop if we have at least OP or SP
                    if "OP" in signals_found or "SP" in signals_found:
                        for sig, orig_col in signals_found.items():
                            new_name = f"{tag_orig}_{sig}"
                            if orig_col != new_name:
                                rename_map[orig_col] = new_name
                                report.append(f"  Renamed: {orig_col!r}  →  {new_name!r}")

                        processed_tags.add(base_upper)
                break

    df_norm = df.rename(columns=rename_map)
    if not rename_map:
        report.append("  No column renames needed.")
    return df_norm, report


# ---------------------------------------------------------------------------
# Fill missing MODE columns
# ---------------------------------------------------------------------------

def _fill_missing_mode(df, auto_mode_value):
    """
    For every loop that has _PV but no _MODE, add a _MODE column filled
    with auto_mode_value. Modifies df in-place; returns report lines.
    """
    report = []
    pv_cols = [c for c in df.columns if c.upper().endswith("_PV") or c.upper().endswith("_MV")]

    for pv_col in pv_cols:
        tag = pv_col[:-3]  # strip "_PV"
        # Look for existing MODE column (case-insensitive)
        mode_col = next(
            (c for c in df.columns if c.upper() == f"{tag.upper()}_MODE"),
            None,
        )
        if mode_col is None:
            new_mode_col = f"{tag}_MODE"
            df[new_mode_col] = auto_mode_value
            report.append(
                f"  Added missing MODE column {new_mode_col!r} — filled with '{auto_mode_value}'"
            )

    return report


# ---------------------------------------------------------------------------
# Normalise MODE column capitalisation
# ---------------------------------------------------------------------------

def _normalise_mode_case(df):
    """
    Rename _mode / _Mode → _MODE so the engine always sees uppercase.
    Modifies df in-place; returns report lines.
    """
    rename_map = {}
    report = []
    for col in df.columns:
        if col.upper().endswith("_MODE") and not col.endswith("_MODE"):
            new_name = col[:-5] + "_MODE"
            rename_map[col] = new_name
            report.append(f"  MODE case fix: {col!r}  →  {new_name!r}")
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    return report


# ---------------------------------------------------------------------------
# Quick self-test  (run:  python column_normaliser.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import textwrap

    def _make_df(cols):
        return pd.DataFrame(columns=["TIMESTAMP"] + cols)

    tests = [
        (
            "Format 1 — underscore",
            _make_df(["FIC-101_PV", "FIC-101_OP", "FIC-101_SP", "FIC-101_MODE",
                      "TIC-102_PV", "TIC-102_OP", "TIC-102_SP", "TIC-102_mode"]),
        ),
        (
            "Format 2 — dot separator",
            _make_df(["FIC-101.PV", "FIC-101.OP", "FIC-101.SP", "FIC-101.MODE",
                      "TIC-102.PV", "TIC-102.OP", "TIC-102.SP"]),
        ),
        (
            "Format 3 — bare tag",
            _make_df(["YN.ETH1.15FC311", "YN.ETH1.15FC311OP", "YN.ETH1.15FC311SP",
                      "YN.ETH1.15LC094", "YN.ETH1.15LC094OP", "YN.ETH1.15LC094SP",
                      "YN.ETH1.15PCT518", "YN.ETH1.15PCT518OP"]),  # partial loop
        ),
    ]

    for label, df_test in tests:
        print(f"\n{'='*60}")
        print(f"  TEST: {label}")
        print(f"{'='*60}")
        print("  Input columns :", list(df_test.columns))
        df_out, rpt = normalise_columns(df_test)
        print("  Output columns:", list(df_out.columns))
        print("  Report:")
        for line in rpt:
            print("   ", line)
