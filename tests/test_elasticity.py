import os
import tempfile
import pandas as pd
import pytest
from src.elasticity import load_elasticity, get_elasticity, DEFAULT_ELASTICITY


def test_default_when_no_file():
    table = load_elasticity(None)
    assert table == {}
    assert get_elasticity(table, "SKU1", 0) == DEFAULT_ELASTICITY


def test_default_when_file_missing():
    table = load_elasticity("/tmp/nonexistent_elasticity.parquet")
    assert get_elasticity(table, "SKU1", 0) == DEFAULT_ELASTICITY


def test_load_from_csv():
    data = pd.DataFrame({
        "tpnd": ["SKU1", "SKU2"],
        "store_cluster_id": [0, 1],
        "elasticity_coeff": [-1.5, -0.8],
    })
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        data.to_csv(f, index=False)
        fname = f.name
    try:
        table = load_elasticity(fname)
        assert get_elasticity(table, "SKU1", 0) == -1.5
        assert get_elasticity(table, "SKU2", 1) == -0.8
        assert get_elasticity(table, "UNKNOWN", 0) == DEFAULT_ELASTICITY
    finally:
        os.unlink(fname)


def test_load_from_parquet():
    data = pd.DataFrame({
        "tpnd": ["SKU3"],
        "store_cluster_id": [2],
        "elasticity_coeff": [-2.1],
    })
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        fname = f.name
    data.to_parquet(fname, index=False)
    try:
        table = load_elasticity(fname)
        assert get_elasticity(table, "SKU3", 2) == -2.1
    finally:
        os.unlink(fname)
