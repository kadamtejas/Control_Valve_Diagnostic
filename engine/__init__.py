"""
engine — the v2 diagnostics package.
======================================

Public entry points used by the v3 wrapper and by `valve_diagnostics_v2.py`
(the top-level shim):

    from engine import run_diagnostics, DEFAULTS, main

The shim re-exports all of these at the top level so existing
`import valve_diagnostics_v2 as v2` patterns keep working.
"""

from .utils import DEFAULTS, logger, safe_float, safe_pos, setup_logging
from .engine import run_diagnostics
from .cli import main

__all__ = [
    "DEFAULTS", "logger", "safe_float", "safe_pos", "setup_logging",
    "run_diagnostics", "main",
]
