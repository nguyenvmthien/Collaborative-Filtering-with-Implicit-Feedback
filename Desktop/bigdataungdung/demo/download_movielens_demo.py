import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ML100K_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"


def download_movielens(url):
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(response.content))


def load_ratings_from_zip(archive):
    with archive.open("ml-100k/u.data") as handle:
        return pd.read_csv(
            handle,
            sep="\t",
            names=["user_id", "item_id", "rating", "timestamp"],
            engine="python",
        )


def sample_subset(df, sample_users, sample_items, seed, min_user_interactions):
    rng = np.random.default_rng(seed)
    sampled = df.copy()

    if sample_users is not None:
        user_counts = sampled["user_id"].value_counts()
        eligible = user_counts[user_counts >= min_user_interactions].index.to_numpy()
        if len(eligible) == 0:
            raise RuntimeError("No users satisfy --min-user-interactions")
        rng.shuffle(eligible)
        sampled = sampled[sampled["user_id"].isin(eligible[:sample_users])].copy()

    if sample_items is not None:
        item_counts = sampled["item_id"].value_counts()
        top_items = item_counts.head(sample_items).index.to_numpy()
        sampled = sampled[sampled["item_id"].isin(top_items)].copy()

    return sampled


def iterative_k_core(df, k, user_col, item_col):
    filtered = df.copy()
    while True:
        before = len(filtered)
        user_counts = filtered[user_col].value_counts()
        filtered = filtered[filtered[user_col].isin(user_counts[user_counts >= k].index)]

        item_counts = filtered[item_col].value_counts()
        filtered = filtered[filtered[item_col].isin(item_counts[item_counts >= k].index)]
        if len(filtered) == before:
            break
    return filtered


def split_leave_two_out(df, user_col, item_col, time_col):
    train_pairs = []
    val_pairs = []
    test_pairs = []

    for user_id, group in df.groupby(user_col, sort=False):
        ordered = group.sort_values(time_col, kind="mergesort")
        items = ordered[item_col].tolist()

        if len(items) < 3:
            train_pairs.extend((user_id, item_id) for item_id in items)
            continue

        test_pairs.append((user_id, items[-1]))
        val_pairs.append((user_id, items[-2]))
        train_pairs.extend((user_id, item_id) for item_id in items[:-2])

    return train_pairs, val_pairs, test_pairs


def to_index_df(pairs, user_to_idx, item_to_idx):
    rows = [(user_to_idx[u], item_to_idx[i]) for u, i in pairs]
    return pd.DataFrame(rows, columns=["user_idx", "item_idx"])


def preprocess_dataframe(
    df,
    dataset_name,
    output_dir,
    user_col,
    item_col,
    timestamp_col,
    k_core,
    rating_col,
    rating_threshold,
):
    work = df.copy()

    if rating_col and rating_col in work.columns:
        before = len(work)
        work = work[pd.to_numeric(work[rating_col], errors="coerce") >= rating_threshold]
        print(f"[filter] {rating_col} >= {rating_threshold}: removed {before - len(work):,} rows")

    if timestamp_col in work.columns:
        ts = pd.to_numeric(work[timestamp_col], errors="coerce")
        work["timestamp"] = ts.fillna(0).astype("int64")
    else:
        work["timestamp"] = np.arange(len(work), dtype=np.int64)

    work = work[[user_col, item_col, "timestamp"]].copy()
    work[user_col] = work[user_col].astype(str)
    work[item_col] = work[item_col].astype(str)
    before = len(work)
    work = work.dropna(subset=[user_col, item_col]).drop_duplicates([user_col, item_col], keep="last")
    print(f"[clean] removed {before - len(work):,} duplicate/invalid rows")

    work = iterative_k_core(work, k_core, user_col=user_col, item_col=item_col)
    user_counts = work[user_col].value_counts()
    work = work[work[user_col].isin(user_counts[user_counts >= 3].index)]

    if work.empty:
        raise RuntimeError("No data left after filtering. Lower k-core or rating threshold.")

    train_pairs, val_pairs, test_pairs = split_leave_two_out(
        work, user_col=user_col, item_col=item_col, time_col="timestamp"
    )

    users = sorted(work[user_col].unique())
    items = sorted(work[item_col].unique())
    user_to_idx = {u: i for i, u in enumerate(users)}
    item_to_idx = {i: j for j, i in enumerate(items)}

    train_df = to_index_df(train_pairs, user_to_idx, item_to_idx)
    val_df = to_index_df(val_pairs, user_to_idx, item_to_idx)
    test_df = to_index_df(test_pairs, user_to_idx, item_to_idx)

    dataset_dir = output_dir / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)

    train_df.to_csv(dataset_dir / "train.csv", index=False)
    val_df.to_csv(dataset_dir / "val.csv", index=False)
    test_df.to_csv(dataset_dir / "test.csv", index=False)
    pd.DataFrame({"original_id": users, "user_idx": range(len(users))}).to_csv(
        dataset_dir / "user_mapping.csv", index=False
    )
    pd.DataFrame({"original_id": items, "item_idx": range(len(items))}).to_csv(
        dataset_dir / "item_mapping.csv", index=False
    )

    info = {
        "dataset": dataset_name,
        "n_users": len(users),
        "n_items": len(items),
        "n_interactions": int(len(work)),
        "density": float(len(work) / (len(users) * len(items))),
        "n_train": int(len(train_df)),
        "n_val": int(len(val_df)),
        "n_test": int(len(test_df)),
        "k_core": int(k_core),
    }

    with (dataset_dir / "info.json").open("w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=2)

    print(
        f"[saved] {dataset_name}: users={info['n_users']:,}, items={info['n_items']:,}, "
        f"interactions={info['n_interactions']:,}, density={info['density'] * 100:.4f}%"
    )
    print(
        f"        split -> train={info['n_train']:,}, val={info['n_val']:,}, test={info['n_test']:,}"
    )


def main():
    parser = argparse.ArgumentParser(description="Download and preprocess a small MovieLens demo dataset")
    parser.add_argument("--url", default=ML100K_URL, help="Download URL")
    parser.add_argument("--dataset-name", default="ml100k_tiny", help="Output dataset folder name")
    parser.add_argument("--output-dir", type=Path, default=Path("demo/data"))
    parser.add_argument("--sample-users", type=int, default=250, help="Number of users to keep")
    parser.add_argument("--sample-items", type=int, default=300, help="Top popular items to keep")
    parser.add_argument("--min-user-interactions", type=int, default=20, help="Only sample users above this count")
    parser.add_argument("--min-rating", type=float, default=4.0, help="Treat ratings >= this threshold as positive")
    parser.add_argument("--k-core", type=int, default=5, help="K-core threshold after filtering")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print(f"Downloading MovieLens data from {args.url}")
    archive = download_movielens(args.url)
    ratings = load_ratings_from_zip(archive)
    print(
        f"Loaded ratings: rows={len(ratings):,}, users={ratings['user_id'].nunique():,}, "
        f"items={ratings['item_id'].nunique():,}"
    )

    sampled = sample_subset(
        ratings,
        sample_users=args.sample_users,
        sample_items=args.sample_items,
        seed=args.seed,
        min_user_interactions=args.min_user_interactions,
    )
    print(
        f"Sampled subset: rows={len(sampled):,}, users={sampled['user_id'].nunique():,}, "
        f"items={sampled['item_id'].nunique():,}"
    )

    preprocess_dataframe(
        df=sampled,
        dataset_name=args.dataset_name,
        output_dir=args.output_dir,
        user_col="user_id",
        item_col="item_id",
        timestamp_col="timestamp",
        k_core=args.k_core,
        rating_col="rating",
        rating_threshold=args.min_rating,
    )
    print(f"Saved processed dataset to {args.output_dir / args.dataset_name}")


if __name__ == "__main__":
    main()
