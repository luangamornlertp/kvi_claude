"""Module 2 — KVI Scoring (Dynamic Classification).

Produces a KVI score (0–100) and tier per SKU per store cluster.

Tiers:
  Super KVI        80–100  must be competitive at all times
  Traffic Driver   50–79
  Background       20–49   profit generator focus
  Long-tail        0–19    handled by attribute similarity
"""

import pandas as pd
import numpy as np


TIER_THRESHOLDS = {
    "Super KVI": 80,
    "Traffic Driver": 50,
    "Background": 20,
    "Long-tail": 0,
}

WEIGHTS = {
    "velocity_score": 0.35,
    "customer_breadth_score": 0.25,
    "purchase_frequency_score": 0.20,
    "discount_inv_score": 0.20,
}


def _minmax(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - lo) / (hi - lo)


def _build_stock_signals(stock_df: pd.DataFrame) -> pd.DataFrame:
    df = stock_df.copy()

    df["velocity_365"] = pd.to_numeric(df["AVG_DAILY_SALES_365"], errors="coerce").fillna(0)
    df["velocity_13wk"] = pd.to_numeric(df["AVG_DAILY_SALES_13WK"], errors="coerce").fillna(0)
    df["velocity_combined"] = 0.6 * df["velocity_13wk"] + 0.4 * df["velocity_365"]

    df["unique_customers"] = pd.to_numeric(df["Unique_Customer"], errors="coerce").fillna(0)
    df["doh"] = pd.to_numeric(df["DOH"], errors="coerce").fillna(999)
    df["avail_stock"] = pd.to_numeric(df["AVAIL_STOCK_VOLUME"], errors="coerce").fillna(0)

    df["existing_kvi_bonus"] = (df["TOP300_KVI"].astype(str).str.upper() == "Y").astype(float) * 10

    df["item_id"] = df["ITEM"].astype(str)
    return df


def _build_txn_signals(txn_df: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    txn = txn_df.copy()
    txn["tpnd"] = txn["tpnd"].astype(str)
    txn["has_discount"] = (pd.to_numeric(txn["discount_amt"], errors="coerce").fillna(0) > 0).astype(int)
    txn["is_loyalty"] = (txn["cc_flag"] == "cc").astype(int)

    txn = txn.merge(
        clusters.rename(columns={"store_id": "store_id_c"}),
        left_on="store_id",
        right_on="store_id_c",
        how="left",
    )
    txn["store_cluster_id"] = txn["store_cluster_id"].fillna(-1).astype(int)

    agg = (
        txn.groupby(["tpnd", "store_cluster_id"])
        .agg(
            purchase_freq=("transaction_uid", "count"),
            discount_rate=("has_discount", "mean"),
            loyalty_share=("is_loyalty", "mean"),
        )
        .reset_index()
    )
    return agg


def score_kvi(
    stock_df: pd.DataFrame,
    txn_df: pd.DataFrame,
    clusters: pd.DataFrame,
) -> pd.DataFrame:
    """Return DataFrame with (ITEM, LOCATION, store_cluster_id, kvi_score, kvi_tier)."""
    stock = _build_stock_signals(stock_df)

    stock = stock.merge(
        clusters.rename(columns={"store_id": "LOCATION_c"}),
        left_on="LOCATION",
        right_on="LOCATION_c",
        how="left",
    )
    stock["store_cluster_id"] = stock["store_cluster_id"].fillna(-1).astype(int)

    txn_signals = _build_txn_signals(txn_df, clusters)
    txn_signals["tpnd"] = txn_signals["tpnd"].astype(str)
    stock["item_id"] = stock["item_id"].astype(str)

    merged = stock.merge(
        txn_signals,
        left_on=["item_id", "store_cluster_id"],
        right_on=["tpnd", "store_cluster_id"],
        how="left",
    )
    merged["purchase_freq"] = merged["purchase_freq"].fillna(0)
    merged["discount_rate"] = merged["discount_rate"].fillna(0.5)

    grp = merged.groupby("store_cluster_id", group_keys=False)

    merged["velocity_score"] = grp["velocity_combined"].transform(_minmax)
    merged["customer_breadth_score"] = grp["unique_customers"].transform(_minmax)
    merged["purchase_frequency_score"] = grp["purchase_freq"].transform(_minmax)
    merged["discount_inv_score"] = 1.0 - grp["discount_rate"].transform(_minmax)

    raw_score = sum(merged[col] * w for col, w in WEIGHTS.items()) * 100
    merged["kvi_score"] = (raw_score + merged["existing_kvi_bonus"]).clip(0, 100).round(2)

    merged["kvi_tier"] = pd.cut(
        merged["kvi_score"],
        bins=[-1, 20, 50, 80, 101],
        labels=["Long-tail", "Background", "Traffic Driver", "Super KVI"],
    )

    out_cols = [
        "ITEM", "ITEM_NAME", "LOCATION", "store_cluster_id",
        "kvi_score", "kvi_tier", "velocity_combined", "unique_customers",
        "doh", "avail_stock", "lasted_price",
        "DIVISION_NAME", "DEPARTMENT_NAME", "SECTION_NAME",
    ]
    available = [c for c in out_cols if c in merged.columns]
    return merged[available].drop_duplicates(subset=["ITEM", "LOCATION"])


def load_and_run(
    stock_path: str,
    txn_path: str,
    clusters_path: str,
) -> pd.DataFrame:
    stock_df = pd.read_csv(stock_path, low_memory=False)
    txn_df = pd.read_csv(txn_path, low_memory=False)
    clusters = pd.read_parquet(clusters_path)
    return score_kvi(stock_df, txn_df, clusters)
