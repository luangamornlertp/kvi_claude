"""Module 3 — Price Elasticity (External Plug-in Interface).

The real elasticity model will be integrated later. Until then, all lookups
fall back to DEFAULT_ELASTICITY (-1.2, unit-elastic proxy).

Interface:
    load_elasticity(path) -> dict[(tpnd, cluster_id), float]
    get_elasticity(table, tpnd, cluster_id) -> float
"""

from __future__ import annotations

import os
from typing import Dict, Tuple, Optional

import pandas as pd


DEFAULT_ELASTICITY = -1.2


def load_elasticity(path: Optional[str] = None) -> Dict[Tuple[str, int], float]:
    """Load a pre-computed elasticity table from parquet or CSV.

    Expected columns: tpnd (str), store_cluster_id (int), elasticity_coeff (float).
    Returns a dict keyed by (tpnd, store_cluster_id).
    Falls back to empty dict (→ DEFAULT_ELASTICITY used everywhere) if path is None or missing.
    """
    if path is None or not os.path.exists(path):
        return {}

    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    required = {"tpnd", "store_cluster_id", "elasticity_coeff"}
    if not required.issubset(df.columns):
        raise ValueError(f"Elasticity file must contain columns: {required}")

    return {
        (str(row.tpnd), int(row.store_cluster_id)): float(row.elasticity_coeff)
        for row in df.itertuples(index=False)
    }


def get_elasticity(
    table: Dict[Tuple[str, int], float],
    tpnd: str,
    cluster_id: int,
) -> float:
    """Return elasticity for a SKU-cluster pair, defaulting to DEFAULT_ELASTICITY."""
    return table.get((str(tpnd), int(cluster_id)), DEFAULT_ELASTICITY)
