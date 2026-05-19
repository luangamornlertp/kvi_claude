"""Module 4 — Inventory-Triggered Rules Engine.

Emits markdown recommendations and flags based on stock signals.

Rules (evaluated in priority order):
  1. Replenish signal   DOH < 7 AND no open orders → hold/raise
  2. Clearance          DOH > Expected_DOH * 1.5 AND Provision=Discontinue → 20–40% down
  3. Zero-sales risk    incident_zoh=1 AND stock > 0 → 15–25% down
  4. Perishable risk    PERISHABLE AND DOH > shelf_life * 0.6 → 10–20% down
  5. Seasonal ramp-down Expected_DOH > 45 AND velocity trend < -15% → 5–15% down

Cannibalization guard: if a sibling SKU in the same SUBCLASS with similar price is at full price,
cap any markdown at 10%.
"""

import pandas as pd
import numpy as np


SIBLING_PRICE_TOLERANCE = 0.15  # within 15% of current price = sibling


def _velocity_trend(row: pd.Series) -> float:
    """Return fractional change from 52-week to 13-week velocity."""
    v365 = float(row.get("AVG_DAILY_SALES_365", 0) or 0)
    v13 = float(row.get("AVG_DAILY_SALES_13WK", 0) or 0)
    if v365 == 0:
        return 0.0
    return (v13 - v365) / v365


def _build_subclass_price_map(stock_df: pd.DataFrame) -> dict:
    """Map (SUBCLASS, LOCATION) → list of (ITEM, lasted_price) for sibling lookup."""
    df = stock_df[["SUBCLASS", "LOCATION", "ITEM", "lasted_price"]].copy()
    df["lasted_price"] = pd.to_numeric(df["lasted_price"], errors="coerce")
    mapping: dict = {}
    for (sub, loc), grp in df.groupby(["SUBCLASS", "LOCATION"]):
        mapping[(sub, loc)] = list(zip(grp["ITEM"].astype(str), grp["lasted_price"].fillna(0)))
    return mapping


def _has_full_price_sibling(
    item: str,
    subclass: str,
    location,
    current_price: float,
    sibling_map: dict,
    markdown_flags: set,
) -> bool:
    siblings = sibling_map.get((subclass, location), [])
    for sib_item, sib_price in siblings:
        if sib_item == str(item):
            continue
        if sib_price == 0:
            continue
        price_diff = abs(sib_price - current_price) / max(current_price, 1)
        if price_diff <= SIBLING_PRICE_TOLERANCE and sib_item not in markdown_flags:
            return True
    return False


def apply_rules(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Return stock_df augmented with inventory_flag, markdown_pct, trigger_reason columns."""
    df = stock_df.copy()

    num_cols = [
        "DOH", "Expected_DOH", "AVAIL_STOCK_VOLUME", "lasted_price",
        "SOH_On_Order_QTY", "AVG_DAILY_SALES_365", "AVG_DAILY_SALES_13WK",
        "SHELFLIFEDUR", "FORECAST_NEXT_7_DAYS",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["PERISHABLE_FLAG"] = df.get("PERISHABLE_FLAG", pd.Series(0, index=df.index))
    df["PERISHABLE_FLAG"] = df["PERISHABLE_FLAG"].astype(str).str.strip().isin(["1", "Y", "True", "true"]).astype(int)

    provision = df.get("Provision_status", pd.Series("", index=df.index)).fillna("").str.lower()
    incident_zoh = df.get("incident_zoh", pd.Series(0, index=df.index))
    incident_zoh = pd.to_numeric(incident_zoh, errors="coerce").fillna(0)

    df["velocity_trend"] = df.apply(_velocity_trend, axis=1)

    sibling_map = _build_subclass_price_map(df)
    markdown_set: set = set()

    inventory_flag = pd.Series("ok", index=df.index, dtype=str)
    markdown_pct = pd.Series(0.0, index=df.index)
    trigger_reason = pd.Series("", index=df.index, dtype=str)

    # Rule 1: replenish
    mask_replenish = (df["DOH"] < 7) & (df["SOH_On_Order_QTY"] == 0) & (df["AVAIL_STOCK_VOLUME"] > 0)
    inventory_flag[mask_replenish] = "hold"
    trigger_reason[mask_replenish] = "replenish_signal"

    # Rule 2: clearance
    mask_clear = (
        (df["DOH"] > df["Expected_DOH"] * 1.5) &
        (provision.isin(["discontinue", "discontinued"]))
    )
    inventory_flag[mask_clear] = "markdown"
    markdown_pct[mask_clear] = 0.30
    trigger_reason[mask_clear] = "clearance"
    markdown_set.update(df.loc[mask_clear, "ITEM"].astype(str).tolist())

    # Rule 3: zero-sales risk
    mask_zoh = (incident_zoh == 1) & (df["AVAIL_STOCK_VOLUME"] > 0)
    new_zoh = mask_zoh & ~mask_clear
    inventory_flag[new_zoh] = "markdown"
    markdown_pct[new_zoh] = 0.20
    trigger_reason[new_zoh] = "zero_sales_risk"
    markdown_set.update(df.loc[new_zoh, "ITEM"].astype(str).tolist())

    # Rule 4: perishable risk
    shelf_threshold = df["SHELFLIFEDUR"] * 0.6
    mask_perish = (df["PERISHABLE_FLAG"] == 1) & (df["DOH"] > shelf_threshold) & (shelf_threshold > 0)
    new_perish = mask_perish & ~mask_clear & ~new_zoh
    inventory_flag[new_perish] = "markdown"
    markdown_pct[new_perish] = 0.15
    trigger_reason[new_perish] = "perishable_overstock"
    markdown_set.update(df.loc[new_perish, "ITEM"].astype(str).tolist())

    # Rule 5: seasonal ramp-down
    mask_seasonal = (df["Expected_DOH"] > 45) & (df["velocity_trend"] < -0.15)
    new_seasonal = mask_seasonal & ~mask_clear & ~new_zoh & ~new_perish
    inventory_flag[new_seasonal] = "markdown"
    markdown_pct[new_seasonal] = 0.10
    trigger_reason[new_seasonal] = "seasonal_ramp_down"
    markdown_set.update(df.loc[new_seasonal, "ITEM"].astype(str).tolist())

    # Cannibalization guard: cap markdown at 10% if a full-price sibling exists
    for idx in df.index:
        if inventory_flag[idx] != "markdown" or markdown_pct[idx] == 0:
            continue
        item = str(df.at[idx, "ITEM"])
        subclass = df.at[idx, "SUBCLASS"]
        location = df.at[idx, "LOCATION"]
        price = float(df.at[idx, "lasted_price"])
        if _has_full_price_sibling(item, subclass, location, price, sibling_map, markdown_set):
            if markdown_pct[idx] > 0.10:
                markdown_pct[idx] = 0.10
                trigger_reason[idx] = trigger_reason[idx] + "|cannibal_capped"

    df["inventory_flag"] = inventory_flag
    df["markdown_pct"] = markdown_pct
    df["trigger_reason"] = trigger_reason
    return df


def load_and_run(stock_path: str) -> pd.DataFrame:
    stock_df = pd.read_csv(stock_path, low_memory=False)
    return apply_rules(stock_df)
