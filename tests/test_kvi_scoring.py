import pandas as pd
import numpy as np
import pytest
from src.kvi_scoring import score_kvi


def _stock():
    return pd.DataFrame({
        "ITEM": ["A", "B", "C"],
        "ITEM_NAME": ["Alpha", "Beta", "Gamma"],
        "LOCATION": [1, 1, 1],
        "FORMAT_DESC": ["HYPERMARKET"] * 3,
        "region": ["North"] * 3,
        "AVG_DAILY_SALES_365": [100.0, 10.0, 1.0],
        "AVG_DAILY_SALES_13WK": [120.0, 8.0, 0.5],
        "Yesterday_SALES": [5.0, 1.0, 0.0],
        "Unique_Customer": [500, 50, 5],
        "TOP300_KVI": ["Y", "N", "N"],
        "AVAIL_STOCK_VOLUME": [200, 20, 5],
        "DOH": [10, 30, 60],
        "lasted_price": [99.0, 49.0, 9.0],
        "DIVISION_NAME": ["FRESH FOOD"] * 3,
        "DEPARTMENT_NAME": ["PRODUCE"] * 3,
        "SECTION_NAME": ["DURIAN"] * 3,
        "final_forecast_unit": [100.0, 10.0, 1.0],
        "FORECAST_NEXT_7_DAYS": [95.0, 9.0, 0.5],
    })


def _txn():
    rows = []
    for item, freq in [("A", 100), ("B", 20), ("C", 2)]:
        for i in range(freq):
            rows.append({
                "tpnd": item,
                "store_id": 1,
                "transaction_uid": f"{item}_{i}",
                "discount_amt": 0 if i % 3 != 0 else 5,
                "cc_flag": "cc" if i % 2 == 0 else "non_cc",
                "total_net_spend_amt": 100.0,
            })
    return pd.DataFrame(rows)


def _clusters():
    return pd.DataFrame({"store_id": [1], "store_cluster_id": [0],
                         "format_desc": ["HYPERMARKET"], "region": ["North"]})


def test_scores_in_range():
    result = score_kvi(_stock(), _txn(), _clusters())
    assert result["kvi_score"].between(0, 100).all()


def test_high_velocity_scores_higher():
    result = score_kvi(_stock(), _txn(), _clusters())
    score_a = result.loc[result["ITEM"] == "A", "kvi_score"].values[0]
    score_c = result.loc[result["ITEM"] == "C", "kvi_score"].values[0]
    assert score_a > score_c


def test_existing_kvi_flag_boosts_score():
    result = score_kvi(_stock(), _txn(), _clusters())
    score_a = result.loc[result["ITEM"] == "A", "kvi_score"].values[0]
    score_b = result.loc[result["ITEM"] == "B", "kvi_score"].values[0]
    # A has TOP300_KVI=Y, so it gets a bonus
    assert score_a >= score_b


def test_tier_assignment():
    result = score_kvi(_stock(), _txn(), _clusters())
    tiers = set(result["kvi_tier"].astype(str))
    valid = {"Super KVI", "Traffic Driver", "Background", "Long-tail"}
    assert tiers.issubset(valid)
