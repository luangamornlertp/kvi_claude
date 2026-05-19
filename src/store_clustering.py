"""Module 1 — Store Clustering (Localization Layer).

Produces a store_cluster_id lookup from stock and transaction data.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans


FORMAT_ORDER = {
    "HYPERMARKET": 0,
    "SUPERMARKET": 1,
    "MINI SUPERMARKET": 2,
}

N_CLUSTERS = 5


def build_store_features_from_stock(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-store features from stock data."""
    agg = (
        stock_df.groupby("LOCATION")
        .agg(
            format_desc=("FORMAT_DESC", "first"),
            region=("region", "first"),
            median_daily_sales=("AVG_DAILY_SALES_365", "median"),
            median_price=("lasted_price", "median"),
            unique_items=("ITEM", "nunique"),
        )
        .reset_index()
    )
    agg["format_code"] = agg["format_desc"].map(FORMAT_ORDER).fillna(1)
    return agg


def build_store_features_from_txn(txn_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-store features from transaction data."""
    txn_df = txn_df.copy()
    txn_df["is_loyalty"] = (txn_df["cc_flag"] == "cc").astype(int)

    store_agg = (
        txn_df.groupby("store_id")
        .agg(
            avg_basket=("total_net_spend_amt", "mean"),
            loyalty_rate=("is_loyalty", "mean"),
            txn_count=("transaction_uid", "count"),
        )
        .reset_index()
    )
    return store_agg


def cluster_stores(
    stock_df: pd.DataFrame,
    txn_df: pd.DataFrame,
    n_clusters: int = N_CLUSTERS,
    random_state: int = 42,
) -> pd.DataFrame:
    """Fit KMeans clusters and return a store_id → cluster_id DataFrame.

    Returns columns: LOCATION, store_cluster_id, format_desc, region
    """
    stock_features = build_store_features_from_stock(stock_df)
    txn_features = build_store_features_from_txn(txn_df)

    merged = stock_features.merge(
        txn_features, left_on="LOCATION", right_on="store_id", how="left"
    )

    feature_cols = [
        "format_code",
        "median_daily_sales",
        "median_price",
        "unique_items",
        "avg_basket",
        "loyalty_rate",
    ]
    X = merged[feature_cols].fillna(0).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
    merged["store_cluster_id"] = km.fit_predict(X_scaled)

    return merged[["LOCATION", "store_cluster_id", "format_desc", "region"]].rename(
        columns={"LOCATION": "store_id"}
    )


def load_and_run(stock_path: str, txn_path: str, n_clusters: int = N_CLUSTERS) -> pd.DataFrame:
    stock_df = pd.read_csv(stock_path, low_memory=False)
    txn_df = pd.read_csv(txn_path, low_memory=False)
    return cluster_stores(stock_df, txn_df, n_clusters=n_clusters)
