"""Module 5 — Dynamic Price Recommender (Heuristic Weighting).

Combines KVI scores, elasticity, and inventory flags into final price recommendations.

Heuristic weights (no competitor pricing in v1):
  Super KVI:       demand 50%, internal_econ 31%, category_dynamics 19%
  Background:      demand 24%, internal_econ 53%, category_dynamics 23%
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from .elasticity import get_elasticity, DEFAULT_ELASTICITY


WEIGHTS = {
    "Super KVI":      {"demand": 0.50, "internal_econ": 0.31, "category_dynamics": 0.19},
    "Traffic Driver": {"demand": 0.45, "internal_econ": 0.37, "category_dynamics": 0.18},
    "Background":     {"demand": 0.24, "internal_econ": 0.53, "category_dynamics": 0.23},
    "Long-tail":      {"demand": 0.20, "internal_econ": 0.58, "category_dynamics": 0.22},
}


def _price_bounds(current_price: float, kvi_score: float) -> Tuple[float, float]:
    """Tighter bands for high-scoring KVIs."""
    flex = (1.0 - kvi_score / 100.0)
    max_price = current_price * (1.0 + flex * 0.15)
    min_price = current_price * (1.0 - flex * 0.30)
    return round(min_price, 2), round(max_price, 2)


def _demand_adjustment(
    current_price: float,
    elasticity: float,
    inventory_flag: str,
    markdown_pct: float,
) -> float:
    """Demand-signal price adjustment.

    If inventory says markdown, apply it. Elasticity bounds the depth:
    a more elastic item (large negative β) tolerates bigger cuts.
    """
    if inventory_flag == "markdown" and markdown_pct > 0:
        max_cut = min(markdown_pct, abs(elasticity) * 0.15)
        return current_price * (1.0 - max_cut)
    if inventory_flag == "hold":
        return current_price * 1.02  # modest lift signal
    return current_price


def _internal_econ_adjustment(current_price: float, cogs: float) -> float:
    """Keep price above a minimum margin threshold (20% over COGS)."""
    floor = cogs * 1.20 if cogs > 0 else 0
    return max(current_price, floor)


def _category_dynamics_adjustment(current_price: float, doh: float, expected_doh: float) -> float:
    """Light inventory-pressure signal independent of the rules engine."""
    if expected_doh > 0 and doh > expected_doh * 1.2:
        return current_price * 0.98
    return current_price


def recommend(
    kvi_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    elasticity_table: Dict[Tuple[str, int], float],
    calendar_date: str,
) -> pd.DataFrame:
    """Join modules and produce one recommendation row per (ITEM, LOCATION).

    kvi_df columns required:     ITEM, LOCATION, store_cluster_id, kvi_score, kvi_tier, lasted_price
    inventory_df columns required: ITEM, LOCATION, inventory_flag, markdown_pct, trigger_reason,
                                   DOH, Expected_DOH, AVAIL_STOCK_Cost_Value
    """
    kvi = kvi_df.copy()
    inv = inventory_df[
        ["ITEM", "LOCATION", "inventory_flag", "markdown_pct", "trigger_reason",
         "DOH", "Expected_DOH", "AVAIL_STOCK_Cost_Value"]
    ].copy()

    df = kvi.merge(inv, on=["ITEM", "LOCATION"], how="left")
    df["inventory_flag"] = df["inventory_flag"].fillna("ok")
    df["markdown_pct"] = pd.to_numeric(df["markdown_pct"], errors="coerce").fillna(0)
    df["trigger_reason"] = df["trigger_reason"].fillna("")
    df["DOH"] = pd.to_numeric(df.get("DOH", 0), errors="coerce").fillna(0)
    df["Expected_DOH"] = pd.to_numeric(df.get("Expected_DOH", 0), errors="coerce").fillna(0)
    df["cogs"] = pd.to_numeric(df.get("AVAIL_STOCK_Cost_Value", 0), errors="coerce").fillna(0)
    df["current_price"] = pd.to_numeric(df["lasted_price"], errors="coerce").fillna(0)
    df["kvi_score"] = pd.to_numeric(df["kvi_score"], errors="coerce").fillna(0)
    df["store_cluster_id"] = df["store_cluster_id"].fillna(-1).astype(int)
    df["kvi_tier"] = df["kvi_tier"].astype(str).fillna("Background")

    rows = []
    for _, row in df.iterrows():
        current_price = row["current_price"]
        if current_price <= 0:
            continue

        tier = row["kvi_tier"]
        w = WEIGHTS.get(tier, WEIGHTS["Background"])
        elast = get_elasticity(elasticity_table, str(row["ITEM"]), int(row["store_cluster_id"]))

        p_demand = _demand_adjustment(current_price, elast, row["inventory_flag"], row["markdown_pct"])
        p_econ = _internal_econ_adjustment(current_price, row["cogs"])
        p_cat = _category_dynamics_adjustment(current_price, row["DOH"], row["Expected_DOH"])

        blended = (
            w["demand"] * p_demand
            + w["internal_econ"] * p_econ
            + w["category_dynamics"] * p_cat
        )

        lo_bound, hi_bound = _price_bounds(current_price, row["kvi_score"])
        recommended = round(float(np.clip(blended, lo_bound, hi_bound)), 2)

        rows.append({
            "calendar_date": calendar_date,
            "item": row["ITEM"],
            "item_name": row.get("ITEM_NAME", ""),
            "location": row["LOCATION"],
            "store_cluster_id": row["store_cluster_id"],
            "kvi_score": round(float(row["kvi_score"]), 2),
            "kvi_tier": tier,
            "current_price": current_price,
            "recommended_price": recommended,
            "price_lower_bound": lo_bound,
            "price_upper_bound": hi_bound,
            "trigger_reason": row["trigger_reason"],
            "elasticity_coeff": elast,
            "inventory_flag": row["inventory_flag"],
        })

    return pd.DataFrame(rows)


def write_to_db(rec_df: pd.DataFrame, db_url: str, table: str = "price_recommendations") -> None:
    """Write recommendations to database. db_url from env var DB_URL."""
    from sqlalchemy import create_engine

    engine = create_engine(db_url)
    rec_df.to_sql(table, engine, schema="pricing", if_exists="append", index=False)
    engine.dispose()
