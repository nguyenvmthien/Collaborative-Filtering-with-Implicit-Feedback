import argparse
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def export_summary_tables(summary: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_table = pd.DataFrame(
        [
            {"metric": "num_users", "value": summary["num_users"]},
            {"metric": "num_items", "value": summary["num_items"]},
            {"metric": "num_interactions", "value": summary["num_interactions"]},
            {"metric": "density", "value": summary["density"]},
            {"metric": "avg_interactions_per_user", "value": summary["avg_interactions_per_user"]},
            {"metric": "avg_users_per_item", "value": summary["avg_users_per_item"]},
        ]
    )
    summary_csv = out_dir / "stats_table.csv"
    summary_table.to_csv(summary_csv, index=False)

    md_path = out_dir / "stats_table.md"
    md_lines = ["| metric | value |", "|---|---:|"]
    for row in summary_table.itertuples(index=False):
        md_lines.append(f"| {row.metric} | {row.value} |")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {"stats_table_csv": str(summary_csv), "stats_table_md": str(md_path)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export summary stats table.")
    parser.add_argument("--summary-json", required=True, help="Path to summary_stats.json")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary_path = Path(args.summary_json)
    out_dir = Path(args.out_dir)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    result = export_summary_tables(summary=payload, out_dir=out_dir)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
