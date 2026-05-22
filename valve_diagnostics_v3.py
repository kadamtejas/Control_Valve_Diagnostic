"""
valve_diagnostics_v3.py — top-level shim.
===========================================

The implementation lives in the `diagnostics/` package. This file exists
so existing run scripts (RUN_AUTO.bat, RUN_MANUAL.bat, run.sh, etc.) keep
working unchanged: they call `python valve_diagnostics_v3.py --input ...`
and that still does exactly what it did before.
"""

from diagnostics.cli import main
from diagnostics import V3_VERSION   # re-exported for backwards-compatibility
from diagnostics import run_v3       # re-exported for backwards-compatibility

if __name__ == "__main__":
    main()
