"""
Capabilities — decides which diagnostics can run on this dataset.
==================================================================

Layer 1, module 4. Inspects the time context and config thresholds and
disables any diagnostic that needs faster/longer data than what's
available. Each disabled diagnostic gets a clear human-readable reason.
"""

from dataclasses import dataclass, field
from typing import Dict

from .utils import safe_float, safe_pos, DEFAULTS
from .time_context import TimeContext


@dataclass
class Capabilities:
    can_stiction: bool
    can_oscillation: bool
    can_harris: bool
    can_propagation: bool
    skip_reasons: dict = field(default_factory=dict)


def determine_capabilities(tc: TimeContext, config: dict) -> Capabilities:
    """Decide which diagnostics are reliable at this sample rate."""
    cap = Capabilities(True, True, True, True)
    dt = tc.dt_seconds

    if dt > safe_float(config.get("MAX_DT_FOR_STICTION_SEC", 300)):
        cap.can_stiction = False
        cap.skip_reasons["stiction"] = (
            f"Sample interval {tc.dt_str()} too coarse — "
            "stiction detection requires data sampled every "
            f"{int(config['MAX_DT_FOR_STICTION_SEC']/60)} min or faster."
        )
    if dt > safe_float(config.get("MAX_DT_FOR_OSCILLATION_SEC", 300)):
        cap.can_oscillation = False
        cap.skip_reasons["oscillation"] = (
            f"Sample interval {tc.dt_str()} too coarse for oscillation analysis."
        )
    if dt > safe_float(config.get("MAX_DT_FOR_HARRIS_SEC", 300)):
        cap.can_harris = False
        cap.skip_reasons["harris"] = (
            f"Sample interval {tc.dt_str()} too coarse for Harris index estimation."
        )
    if dt > safe_float(config.get("MAX_DT_FOR_PROPAGATION_SEC", 600)):
        cap.can_propagation = False
        cap.skip_reasons["propagation"] = (
            f"Sample interval {tc.dt_str()} too coarse for cross-loop propagation."
        )
    return cap
