import argparse
from pathlib import Path

import pandas as pd


def iterative_kcore_filter(
    df: pd.DataFrame,
    user_col: str,
    item_col: str,
    min_user_interactions: int,
    min_item_interactions: int,
) -> pd.DataFrame:
    filtered = df.copy()
    while True:
        before = len(filtered)

        user_degree = filtered[user_col].value_counts()
        keep_users = user_degree[user_degree >= min_user_interactions].index
        filtered = filtered[filtered[user_col].isin(keep_users)]

        item_degree = filtered[item_col].value_counts()
        keep_items = item_degree[item_degree >= min_item_interactions].index
        filtered = filtered[filtered[item_col].isin(keep_items)]

        if len(filtered) == before:
            break

    return filtered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply iterative k-core filtering.")
    parser.add_argument("--input", required=True, help="Input CSV file path")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    parser.add_argument("--user-col", default="user_id")
    parser.add_argument("--item-col", default="item_id")
    parser.add_argument("--min-user-interactions", type=int, default=10)
    parser.add_argument("--min-item-interactions", type=int, default=5)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    df = pd.read_csv(input_path)
    filtered = iterative_kcore_filter(
        df=df,
        user_col=args.user_col,
        item_col=args.item_col,
        min_user_interactions=args.min_user_interactions,
        min_item_interactions=args.min_item_interactions,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(output_path, index=False)


if __name__ == "__main__":
    main()
