"""Main pipeline — orchestrates all five modules.

Usage:
    python -m pricing_model.src.pipeline \
        --stock data/rtp_stock_data.csv \
        --txn   data/txn_example.csv \
        --date  2026-04-01 \
        [--elasticity path/to/elasticity.parquet] \
        [--output-parquet path/to/out.parquet] \
        [--db-url postgresql+psycopg2://user:pass@host/db]
"""

import argparse
import os
import sys
from datetime import date

import pandas as pd

from .store_clustering import cluster_stores
from .kvi_scoring import score_kvi
from .elasticity import load_elasticity
from .inventory_rules import apply_rules
from .price_recommender import recommend, write_to_db


def run(
    stock_path: str,
    txn_path: str,
    calendar_date: str,
    elasticity_path: str | None = None,
    n_clusters: int = 5,
    output_parquet: str | None = None,
    db_url: str | None = None,
) -> pd.DataFrame:
    print(f"[pipeline] Loading data …")
    stock_df = pd.read_csv(stock_path, low_memory=False)
    txn_df = pd.read_csv(txn_path, low_memory=False)

    print(f"[pipeline] Module 1 — store clustering (k={n_clusters}) …")
    clusters = cluster_stores(stock_df, txn_df, n_clusters=n_clusters)

    print(f"[pipeline] Module 2 — KVI scoring …")
    kvi_df = score_kvi(stock_df, txn_df, clusters)

    print(f"[pipeline] Module 3 — loading elasticity table …")
    elast_table = load_elasticity(elasticity_path)
    if not elast_table:
        print(f"[pipeline]   No elasticity file found — using default {-1.2}")

    print(f"[pipeline] Module 4 — inventory rules …")
    inv_df = apply_rules(stock_df)

    print(f"[pipeline] Module 5 — price recommendations …")
    rec_df = recommend(kvi_df, inv_df, elast_table, calendar_date)

    print(f"[pipeline] {len(rec_df):,} recommendations generated.")

    if output_parquet:
        rec_df.to_parquet(output_parquet, index=False)
        print(f"[pipeline] Saved to {output_parquet}")

    if db_url:
        print(f"[pipeline] Writing to database …")
        write_to_db(rec_df, db_url)
        print(f"[pipeline] Done.")

    return rec_df


def main():
    parser = argparse.ArgumentParser(description="Precision Pricing Pipeline")
    parser.add_argument("--stock", required=True)
    parser.add_argument("--txn", required=True)
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--elasticity", default=None)
    parser.add_argument("--n-clusters", type=int, default=5)
    parser.add_argument("--output-parquet", default=None)
    parser.add_argument("--db-url", default=os.environ.get("DB_URL"))
    args = parser.parse_args()

    rec_df = run(
        stock_path=args.stock,
        txn_path=args.txn,
        calendar_date=args.date,
        elasticity_path=args.elasticity,
        n_clusters=args.n_clusters,
        output_parquet=args.output_parquet,
        db_url=args.db_url,
    )
    print(rec_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
