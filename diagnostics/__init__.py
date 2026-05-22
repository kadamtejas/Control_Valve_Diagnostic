"""
diagnostics — the v3 wrapper package.
======================================

Public entry points:
    from diagnostics import run_v3, main
    from diagnostics import V3_VERSION
"""

from .constants import V3_VERSION
from .pipeline import run_v3
from .cli import main

__all__ = ["V3_VERSION", "run_v3", "main"]
