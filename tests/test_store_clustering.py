import pandas as pd
import pytest
from src.store_clustering import cluster_stores


def _make_stock(n=20):
    return pd.DataFrame({
        "LOCATION": range(n),
        "FORMAT_DESC": (["HYPERMARKET"] * 5 + ["SUPERMARKET"] * 5 + ["MINI SUPERMARKET"] * 10)[:n],
        "region": ["North"] * 10 + ["South"] * 10,
        "AVG_DAILY_SALES_365": [100.0] * n,
        "lasted_price": [50.0] * n,
        "ITEM": [f"SKU{i}" for i in range(n)],
    })


def _make_txn(store_ids):
    rows = []
    for sid in store_ids:
        for i in range(5):
            rows.append({
                "store_id": sid,
                "total_net_spend_amt": 200.0,
                "transaction_uid": f"T{sid}_{i}",
                "cc_flag": "cc" if i % 2 == 0 else "non_cc",
            })
    return pd.DataFrame(rows)


def test_cluster_output_shape():
    stock = _make_stock()
    txn = _make_txn(range(20))
    result = cluster_stores(stock, txn, n_clusters=3)
    assert set(result.columns) >= {"store_id", "store_cluster_id"}
    assert len(result) == 20


def test_cluster_ids_in_range():
    stock = _make_stock()
    txn = _make_txn(range(20))
    result = cluster_stores(stock, txn, n_clusters=3)
    assert result["store_cluster_id"].between(0, 2).all()


def test_no_crash_missing_txn_stores():
    stock = _make_stock()
    txn = _make_txn(range(5))  # only 5 of 20 stores have txns
    result = cluster_stores(stock, txn, n_clusters=3)
    assert len(result) == 20
