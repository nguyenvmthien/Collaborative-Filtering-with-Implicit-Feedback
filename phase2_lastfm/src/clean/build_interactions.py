import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml

from src.clean.filter_kcore import iterative_kcore_filter
from src.clean.normalize_entities import (
    canonical_artist_key,
    normalize_artist_name,
    normalize_mbid,
    normalize_username,
    parse_int,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid YAML config at {path}")
    return payload


def list_library_raw_files(raw_dir: Path) -> List[Path]:
    manifest_path = raw_dir / "raw_manifest.jsonl"
    files: List[Path] = []
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("method") != "library.getArtists":
                continue
            response_file = payload.get("response_file")
            if isinstance(response_file, str):
                p = Path(response_file)
                if p.exists():
                    files.append(p)
        if files:
            return sorted(set(files))

    files = sorted((raw_dir / "library.getArtists").glob("**/page_*.json"))
    return files


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_library_file(path: Path) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    body = payload.get("payload", {}) if isinstance(payload, dict) else {}
    if not isinstance(meta, dict) or not isinstance(body, dict):
        return []

    username = normalize_username(str(meta.get("username", "")))
    crawl_timestamp_utc = str(meta.get("fetched_at_utc", "")).strip()

    artists_obj = body.get("artists", {})
    if not isinstance(artists_obj, dict):
        return []
    if not username:
        attr = artists_obj.get("@attr", {})
        if isinstance(attr, dict):
            username = normalize_username(str(attr.get("user", "")))

    rows: List[Dict[str, Any]] = []
    for artist in ensure_list(artists_obj.get("artist")):
        if not isinstance(artist, dict):
            continue
        artist_name = str(artist.get("name", "")).strip()
        artist_mbid = normalize_mbid(str(artist.get("mbid", "")))
        artist_name_norm = normalize_artist_name(artist_name)
        item_key = canonical_artist_key(artist_name, artist_mbid)
        if not username or not item_key:
            continue
        rows.append(
            {
                "source_username": username,
                "user_key": username,
                "artist_name": artist_name,
                "artist_name_normalized": artist_name_norm,
                "artist_mbid": artist_mbid,
                "item_key": item_key,
                "playcount": parse_int(artist.get("playcount"), 0),
                "label": 1,
                "crawl_timestamp_utc": crawl_timestamp_utc,
                "raw_file": str(path),
            }
        )
    return rows


def stable_sort_deduplicate(audit_df: pd.DataFrame) -> pd.DataFrame:
    if audit_df.empty:
        return audit_df

    sorted_df = audit_df.sort_values(
        by=["user_key", "item_key", "crawl_timestamp_utc", "raw_file"],
        kind="mergesort",
    )
    dedup = (
        sorted_df.groupby(["user_key", "item_key"], as_index=False)
        .agg(
            source_username=("source_username", "first"),
            artist_name=("artist_name", "first"),
            artist_name_normalized=("artist_name_normalized", "first"),
            artist_mbid=("artist_mbid", "first"),
            playcount=("playcount", "max"),
            label=("label", "max"),
            crawl_timestamp_utc=("crawl_timestamp_utc", "max"),
            raw_file=("raw_file", "first"),
        )
        .sort_values(by=["user_key", "item_key"], kind="mergesort")
        .reset_index(drop=True)
    )
    return dedup


def build_entity_tables(filtered_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    users_df = (
        filtered_df.groupby("user_key", as_index=False)
        .agg(source_username=("source_username", "first"))
        .sort_values("user_key", kind="mergesort")
        .reset_index(drop=True)
    )
    users_df["user_id"] = range(len(users_df))
    users_df = users_df[["user_id", "user_key", "source_username"]]

    items_df = (
        filtered_df.groupby("item_key", as_index=False)
        .agg(
            artist_name=("artist_name", "first"),
            artist_name_normalized=("artist_name_normalized", "first"),
            artist_mbid=("artist_mbid", "first"),
        )
        .sort_values("item_key", kind="mergesort")
        .reset_index(drop=True)
    )
    items_df["item_id"] = range(len(items_df))
    items_df = items_df[
        ["item_id", "item_key", "artist_name", "artist_name_normalized", "artist_mbid"]
    ]
    return users_df, items_df


def compute_file_metadata(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_binary_edges(path: Path, interactions_df: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for row in interactions_df[["user_id", "item_id"]].itertuples(index=False):
            writer.writerow([int(row.user_id), int(row.item_id)])


def run_build(config_path: Path, raw_dir: Path, out_dir: Path) -> None:
    config = read_yaml(config_path)
    clean_cfg = config.get("clean", {})
    project_cfg = config.get("project", {})

    min_user = int(clean_cfg.get("min_user_interactions", 10))
    min_item = int(clean_cfg.get("min_item_interactions", 5))

    interim_dir = raw_dir.parent / "interim"
    interim_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_files = list_library_raw_files(raw_dir)
    if not raw_files:
        raise RuntimeError(f"No library raw files found in {raw_dir}")

    rows: List[Dict[str, Any]] = []
    for file_path in raw_files:
        rows.extend(parse_library_file(file_path))

    if not rows:
        raise RuntimeError("Parsed zero interaction rows from raw files.")

    audit_df = pd.DataFrame(rows)
    audit_df = audit_df[(audit_df["user_key"] != "") & (audit_df["item_key"] != "")]
    audit_dedup = stable_sort_deduplicate(audit_df)

    filtered = iterative_kcore_filter(
        df=audit_dedup,
        user_col="user_key",
        item_col="item_key",
        min_user_interactions=min_user,
        min_item_interactions=min_item,
    )
    filtered = filtered.sort_values(by=["user_key", "item_key"], kind="mergesort").reset_index(
        drop=True
    )
    if filtered.empty:
        raise RuntimeError("All rows removed by filtering. Relax k-core thresholds.")

    users_df, items_df = build_entity_tables(filtered)
    user_map = dict(zip(users_df["user_key"], users_df["user_id"]))
    item_map = dict(zip(items_df["item_key"], items_df["item_id"]))

    interactions_df = filtered.copy()
    interactions_df["user_id"] = interactions_df["user_key"].map(user_map)
    interactions_df["item_id"] = interactions_df["item_key"].map(item_map)
    interactions_df["label"] = 1
    interactions_df = interactions_df[
        ["user_id", "item_id", "label", "playcount", "crawl_timestamp_utc"]
    ].sort_values(by=["user_id", "item_id"], kind="mergesort")
    interactions_df = interactions_df.reset_index(drop=True)

    interactions_file = out_dir / str(clean_cfg.get("interactions_file", "interactions.csv"))
    users_file = out_dir / str(clean_cfg.get("users_file", "users.csv"))
    items_file = out_dir / str(clean_cfg.get("items_file", "items.csv"))
    binary_file = out_dir / str(clean_cfg.get("binary_edges_file", "interactions_binary.tsv"))
    manifest_file = out_dir / str(clean_cfg.get("manifest_file", "manifest.json"))
    audit_file = interim_dir / str(clean_cfg.get("audit_file", "audit_interactions.csv"))

    audit_dedup.to_csv(audit_file, index=False)
    users_df.to_csv(users_file, index=False)
    items_df.to_csv(items_file, index=False)
    interactions_df.to_csv(interactions_file, index=False)
    write_binary_edges(binary_file, interactions_df)

    crawl_ts_min = interactions_df["crawl_timestamp_utc"].min()
    crawl_ts_max = interactions_df["crawl_timestamp_utc"].max()

    manifest_payload = {
        "generated_at_utc": utc_now_iso(),
        "config_path": str(config_path),
        "raw_dir": str(raw_dir),
        "random_seed": int(project_cfg.get("random_seed", 0)),
        "filtering": {
            "min_user_interactions": min_user,
            "min_item_interactions": min_item,
        },
        "counts": {
            "raw_rows": int(len(audit_df)),
            "raw_deduplicated_rows": int(len(audit_dedup)),
            "filtered_rows": int(len(interactions_df)),
            "num_users": int(users_df["user_id"].nunique()),
            "num_items": int(items_df["item_id"].nunique()),
        },
        "crawl_timestamp_utc_range": {
            "min": str(crawl_ts_min),
            "max": str(crawl_ts_max),
        },
        "files": {
            "audit_interactions": compute_file_metadata(audit_file),
            "users": compute_file_metadata(users_file),
            "items": compute_file_metadata(items_file),
            "interactions": compute_file_metadata(interactions_file),
            "interactions_binary": compute_file_metadata(binary_file),
        },
    }
    manifest_file.write_text(
        json.dumps(manifest_payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build cleaned Last.fm interactions dataset.")
    parser.add_argument("--config", required=True, help="Path to YAML config file.")
    parser.add_argument("--raw-dir", required=True, help="Raw API directory path.")
    parser.add_argument("--out-dir", required=True, help="Processed output directory path.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    config_path = Path(args.config).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw dir not found: {raw_dir}")

    run_build(config_path=config_path, raw_dir=raw_dir, out_dir=out_dir)


if __name__ == "__main__":
    main()
