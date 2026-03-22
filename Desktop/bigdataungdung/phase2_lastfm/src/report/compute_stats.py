import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.report.export_tables import export_summary_tables
from src.report.make_figures import generate_degree_histograms


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_density(num_users: int, num_items: int, num_interactions: int) -> float:
    denominator = num_users * num_items
    if denominator == 0:
        return 0.0
    return float(num_interactions / denominator)


def maybe_load_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    return pd.read_csv(path)


def run_stats(input_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    interactions = pd.read_csv(input_path)
    if interactions.empty:
        raise RuntimeError("Input interactions file is empty.")

    data_dir = input_path.parent
    items_df = maybe_load_csv(data_dir / "items.csv")
    users_df = maybe_load_csv(data_dir / "users.csv")

    num_users = int(interactions["user_id"].nunique())
    num_items = int(interactions["item_id"].nunique())
    num_interactions = int(len(interactions))
    density = compute_density(num_users, num_items, num_interactions)
    avg_interactions_per_user = float(num_interactions / num_users) if num_users > 0 else 0.0
    avg_users_per_item = float(num_interactions / num_items) if num_items > 0 else 0.0

    item_degree = (
        interactions.groupby("item_id", as_index=False)
        .size()
        .rename(columns={"size": "user_count"})
        .sort_values(by=["user_count", "item_id"], ascending=[False, True], kind="mergesort")
    )
    top20 = item_degree.head(20).copy()
    if items_df is not None and not items_df.empty:
        top20 = top20.merge(
            items_df[["item_id", "artist_name", "item_key"]],
            on="item_id",
            how="left",
        )
    top20_path = out_dir / "top_20_artists.csv"
    top20.to_csv(top20_path, index=False)

    summary = {
        "generated_at_utc": utc_now_iso(),
        "input_file": str(input_path),
        "num_users": num_users,
        "num_items": num_items,
        "num_interactions": num_interactions,
        "density": density,
        "avg_interactions_per_user": avg_interactions_per_user,
        "avg_users_per_item": avg_users_per_item,
        "user_degree_min": int(interactions["user_id"].value_counts().min()),
        "user_degree_max": int(interactions["user_id"].value_counts().max()),
        "item_degree_min": int(interactions["item_id"].value_counts().min()),
        "item_degree_max": int(interactions["item_id"].value_counts().max()),
        "has_users_file": users_df is not None,
        "has_items_file": items_df is not None,
    }
    summary_json = out_dir / "summary_stats.json"
    summary_json.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")

    figure_paths = generate_degree_histograms(interactions_df=interactions, out_dir=out_dir)
    table_paths = export_summary_tables(summary=summary, out_dir=out_dir)

    manifest = {
        "generated_at_utc": utc_now_iso(),
        "files": {
            "summary_stats": str(summary_json),
            "top_20_artists": str(top20_path),
            **figure_paths,
            **table_paths,
        },
    }
    manifest_path = out_dir / "stats_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute dataset statistics for Phase 2 report.")
    parser.add_argument("--input", required=True, help="Path to interactions.csv")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_stats(input_path=Path(args.input).resolve(), out_dir=Path(args.out_dir).resolve())


if __name__ == "__main__":
    main()
