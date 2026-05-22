"""
Plant KPIs — aggregate per-loop diagnoses into plant-level metrics.
=====================================================================

Layer 3, module 2. Plant Health Index (mean of all loop health scores),
%-good / %-poor / %-critical, diagnosis-type counts, and the top-N worst
loops list.
"""

from dataclasses import dataclass, field

import numpy as np

from .utils import safe_float


@dataclass
class PlantKPIs:
    n_loops_total: int = 0
    n_loops_analysed: int = 0
    n_skipped: int = 0
    pct_good: float = 0.0
    pct_poor: float = 0.0
    pct_critical: float = 0.0
    plant_health_index: float = 100.0
    diagnosis_counts: dict = field(default_factory=dict)
    top_n_worst: list = field(default_factory=list)


def compute_plant_kpis(per_loop: dict, config: dict) -> PlantKPIs:
    """Aggregate per-loop diagnoses into plant-level KPIs."""
    kpi = PlantKPIs()
    kpi.n_loops_total = len(per_loop)
    health_scores = []
    diag_counts = {}
    for name, info in per_loop.items():
        diag = info.get("diagnosis")
        if diag is None:
            kpi.n_skipped += 1
            continue
        kpi.n_loops_analysed += 1
        health_scores.append(diag.health_score)
        diag_counts[diag.primary] = diag_counts.get(diag.primary, 0) + 1

    if health_scores:
        kpi.plant_health_index = round(float(np.mean(health_scores)), 1)
        good = safe_float(config.get("PLANT_HEALTH_GOOD_THRESHOLD", 75))
        poor = safe_float(config.get("PLANT_HEALTH_POOR_THRESHOLD", 50))
        kpi.pct_good = round(100.0 * np.mean([s >= good for s in health_scores]), 1)
        kpi.pct_critical = round(100.0 * np.mean([s < poor for s in health_scores]), 1)
        kpi.pct_poor = round(100.0 - kpi.pct_good - kpi.pct_critical, 1)

    kpi.diagnosis_counts = diag_counts

    # Top-N worst loops by health_score
    n_top = int(safe_float(config.get("TOP_N_WORST_LOOPS", 10)))
    rank = sorted(
        [(name, info["diagnosis"].health_score, info["diagnosis"].primary)
         for name, info in per_loop.items() if info.get("diagnosis") is not None],
        key=lambda x: x[1]
    )
    kpi.top_n_worst = rank[:n_top]
    return kpi
