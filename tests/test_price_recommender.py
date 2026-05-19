import pandas as pd
import pytest
from src.price_recommender import recommend, _price_bounds
from src.elasticity import DEFAULT_ELASTICITY


def _kvi_df():
    return pd.DataFrame({
        "ITEM": ["A", "B", "C", "D"],
        "ITEM_NAME": ["Alpha", "Beta", "Gamma", "Delta"],
        "LOCATION": [1, 1, 1, 1],
        "store_cluster_id": [0, 0, 0, 0],
        "kvi_score": [90.0, 60.0, 30.0, 5.0],
        "kvi_tier": ["Super KVI", "Traffic Driver", "Background", "Long-tail"],
        "lasted_price": [100.0, 50.0, 20.0, 10.0],
    })


def _inv_df():
    return pd.DataFrame({
        "ITEM": ["A", "B", "C", "D"],
        "LOCATION": [1, 1, 1, 1],
        "inventory_flag": ["ok", "markdown", "ok", "ok"],
        "markdown_pct": [0.0, 0.15, 0.0, 0.0],
        "trigger_reason": ["", "perishable_overstock", "", ""],
        "DOH": [15, 5, 20, 30],
        "Expected_DOH": [20, 10, 20, 20],
        "AVAIL_STOCK_Cost_Value": [60, 30, 10, 5],
    })


def test_output_columns():
    result = recommend(_kvi_df(), _inv_df(), {}, "2026-04-01")
    required = {
        "calendar_date", "item", "location", "kvi_score", "kvi_tier",
        "current_price", "recommended_price", "price_lower_bound", "price_upper_bound",
        "inventory_flag", "elasticity_coeff",
    }
    assert required.issubset(result.columns)


def test_super_kvi_tight_bounds():
    result = recommend(_kvi_df(), _inv_df(), {}, "2026-04-01")
    row = result[result["item"] == "A"].iloc[0]
    band = row["price_upper_bound"] - row["price_lower_bound"]
    # Super KVI score=90 → flex=0.10, band = 100*(0.15+0.30)*0.10 = 4.5
    assert band < 6.0


def test_recommended_within_bounds():
    result = recommend(_kvi_df(), _inv_df(), {}, "2026-04-01")
    for _, row in result.iterrows():
        assert row["price_lower_bound"] <= row["recommended_price"] <= row["price_upper_bound"], \
            f"{row['item']}: {row['recommended_price']} not in [{row['price_lower_bound']}, {row['price_upper_bound']}]"


def test_markdown_lowers_price():
    result = recommend(_kvi_df(), _inv_df(), {}, "2026-04-01")
    row_b = result[result["item"] == "B"].iloc[0]
    assert row_b["recommended_price"] < row_b["current_price"]


def test_elasticity_default_used():
    result = recommend(_kvi_df(), _inv_df(), {}, "2026-04-01")
    assert (result["elasticity_coeff"] == DEFAULT_ELASTICITY).all()


def test_price_bounds_super_kvi():
    lo, hi = _price_bounds(100.0, 90.0)
    assert hi - lo < 10.0  # tight band


def test_price_bounds_longtail():
    lo, hi = _price_bounds(100.0, 5.0)
    assert hi - lo > 30.0  # wide band
