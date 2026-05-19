import pandas as pd
import pytest
from src.inventory_rules import apply_rules


def _base_row(**overrides):
    base = {
        "ITEM": "SKU1", "ITEM_NAME": "Test", "LOCATION": 1, "SUBCLASS": "SUB1",
        "DOH": 20.0, "Expected_DOH": 30.0, "AVAIL_STOCK_VOLUME": 100.0,
        "SOH_On_Order_QTY": 0.0, "lasted_price": 100.0, "cogs": 60.0,
        "PERISHABLE_FLAG": 0, "SHELFLIFEDUR": 7.0,
        "AVG_DAILY_SALES_365": 10.0, "AVG_DAILY_SALES_13WK": 10.0,
        "FORECAST_NEXT_7_DAYS": 70.0, "AVAIL_STOCK_Cost_Value": 60.0,
        "Provision_status": "Current", "incident_zoh": 0,
    }
    base.update(overrides)
    return base


def test_replenish_signal():
    df = pd.DataFrame([_base_row(DOH=5.0, SOH_On_Order_QTY=0.0)])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "hold"
    assert result["trigger_reason"].iloc[0] == "replenish_signal"


def test_clearance():
    df = pd.DataFrame([_base_row(DOH=60.0, Expected_DOH=30.0, Provision_status="Discontinue")])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "markdown"
    assert result["markdown_pct"].iloc[0] == 0.30


def test_zero_sales_risk():
    df = pd.DataFrame([_base_row(incident_zoh=1, AVAIL_STOCK_VOLUME=50)])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "markdown"
    assert "zero_sales_risk" in result["trigger_reason"].iloc[0]


def test_perishable_overstock():
    df = pd.DataFrame([_base_row(PERISHABLE_FLAG=1, DOH=5.0, SHELFLIFEDUR=7.0)])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "markdown"
    assert "perishable" in result["trigger_reason"].iloc[0]


def test_seasonal_ramp_down():
    df = pd.DataFrame([_base_row(
        Expected_DOH=50.0, AVG_DAILY_SALES_365=10.0, AVG_DAILY_SALES_13WK=8.0
    )])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "markdown"
    assert "seasonal" in result["trigger_reason"].iloc[0]


def test_ok_when_no_triggers():
    df = pd.DataFrame([_base_row(DOH=15.0, SOH_On_Order_QTY=100.0)])
    result = apply_rules(df)
    assert result["inventory_flag"].iloc[0] == "ok"


def test_cannibalization_cap():
    rows = [
        _base_row(ITEM="SKU1", DOH=60.0, Expected_DOH=30.0, Provision_status="Discontinue",
                  lasted_price=100.0),
        _base_row(ITEM="SKU2", lasted_price=105.0, DOH=10.0),  # full-price sibling
    ]
    df = pd.DataFrame(rows)
    result = apply_rules(df)
    sku1 = result[result["ITEM"] == "SKU1"]
    assert sku1["markdown_pct"].iloc[0] <= 0.10
    assert "cannibal_capped" in sku1["trigger_reason"].iloc[0]
