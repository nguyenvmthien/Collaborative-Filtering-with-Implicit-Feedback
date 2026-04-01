import argparse
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt
import pandas as pd


def generate_degree_histograms(interactions_df: pd.DataFrame, out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    user_degree = interactions_df["user_id"].value_counts()
    item_degree = interactions_df["item_id"].value_counts()

    user_fig = out_dir / "degree_hist_users.png"
    item_fig = out_dir / "degree_hist_items.png"

    plt.figure(figsize=(8, 5))
    plt.hist(user_degree.values, bins=50, color="#2f4f4f", edgecolor="white")
    plt.title("User Degree Distribution")
    plt.xlabel("Interactions per User")
    plt.ylabel("Count of Users")
    plt.tight_layout()
    plt.savefig(user_fig, dpi=150)
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.hist(item_degree.values, bins=50, color="#8b0000", edgecolor="white")
    plt.title("Item Degree Distribution")
    plt.xlabel("Users per Item")
    plt.ylabel("Count of Items")
    plt.tight_layout()
    plt.savefig(item_fig, dpi=150)
    plt.close()

    return {"user_degree_hist": str(user_fig), "item_degree_hist": str(item_fig)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate degree histogram figures.")
    parser.add_argument("--input", required=True, help="Path to interactions.csv")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    interactions = pd.read_csv(Path(args.input))
    paths = generate_degree_histograms(interactions_df=interactions, out_dir=Path(args.out_dir))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
