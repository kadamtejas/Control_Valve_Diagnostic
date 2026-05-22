"""
valve_diagnostics_v2.py — top-level shim.
===========================================

The implementation lives in the `engine/` package. This shim exists so:

  * Existing `import valve_diagnostics_v2 as v2` calls keep working
  * The v3 wrapper's `v2.run_diagnostics(...)` and `v2.DEFAULTS` references
    continue to resolve to the same objects
  * Running this file directly behaves the same as `python -m engine.cli`

Update imports here only when the engine package's public surface changes.
"""

# Re-export the engine's public API so legacy attribute access works:
#   v2.run_diagnostics(...)   v2.DEFAULTS   v2.logger   v2.safe_float
from engine import (
    run_diagnostics,
    DEFAULTS,
    logger,
    safe_float,
    safe_pos,
    setup_logging,
)
from engine.cli import main

if __name__ == "__main__":
    main()
