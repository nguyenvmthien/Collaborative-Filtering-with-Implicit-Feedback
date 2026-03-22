import argparse
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from src.clean.filter_kcore import iterative_kcore_filter
from src.clean.normalize_entities import canonical_artist_key, normalize_username, parse_int
from src.collect.lastfm_client import LastFMClient, LastFMAPIError, LastFMClientError
from src.collect.resume_state import CrawlState, ResumeStateStore, page_key


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(project_root: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid YAML config at {path}")
    return payload


def read_seed_users(seed_file: Path) -> List[str]:
    users: List[str] = []
    seen = set()
    for raw_line in seed_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        username = normalize_username(line)
        if username and username not in seen:
            seen.add(username)
            users.append(username)
    return users


def parse_total_pages(payload_section: Any, default: int = 1) -> int:
    if not isinstance(payload_section, dict):
        return default
    attr = payload_section.get("@attr", {})
    if not isinstance(attr, dict):
        return default
    total_pages = attr.get("totalPages") or attr.get("totalpages") or attr.get("total_pages")
    value = parse_int(total_pages, default)
    return max(value, 1)


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_friend_usernames(payload: Dict[str, Any]) -> List[str]:
    friends_obj = payload.get("friends", {})
    if not isinstance(friends_obj, dict):
        return []
    raw_friends = ensure_list(friends_obj.get("user"))
    out: List[str] = []
    for entry in raw_friends:
        if isinstance(entry, dict):
            candidate = entry.get("name", "")
        else:
            candidate = str(entry)
        normalized = normalize_username(str(candidate))
        if normalized:
            out.append(normalized)
    return out


def extract_artists(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    artists_obj = payload.get("artists", {})
    if not isinstance(artists_obj, dict):
        return []
    raw_artists = ensure_list(artists_obj.get("artist"))
    out: List[Dict[str, Any]] = []
    for artist in raw_artists:
        if not isinstance(artist, dict):
            continue
        name = str(artist.get("name", "")).strip()
        mbid = str(artist.get("mbid", "")).strip()
        playcount = parse_int(artist.get("playcount"), 0)
        if not name and not mbid:
            continue
        out.append(
            {
                "artist_name": name,
                "artist_mbid": mbid,
                "playcount": playcount,
                "artist_key": canonical_artist_key(name, mbid),
            }
        )
    return out


def safe_path_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe or "unknown"


class RawManifestWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_keys = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = payload.get("record_key")
                    if isinstance(key, str):
                        self._seen_keys.add(key)

    def append_once(self, payload: Dict[str, Any]) -> bool:
        key = str(payload.get("record_key", ""))
        if not key:
            raise ValueError("Manifest record requires record_key.")
        if key in self._seen_keys:
            return False
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self._seen_keys.add(key)
        return True


class RawEdgeIndex:
    def __init__(self, sqlite_path: Path) -> None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(sqlite_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_edges (
              user_key TEXT NOT NULL,
              artist_key TEXT NOT NULL,
              artist_name TEXT NOT NULL,
              artist_mbid TEXT NOT NULL,
              playcount INTEGER NOT NULL,
              first_seen_utc TEXT NOT NULL,
              PRIMARY KEY (user_key, artist_key)
            )
            """
        )
        self.conn.commit()

    def add_edges(self, user_key: str, artists: List[Dict[str, Any]], first_seen_utc: str) -> int:
        rows = []
        for artist in artists:
            artist_key = str(artist.get("artist_key", ""))
            if not artist_key:
                continue
            rows.append(
                (
                    user_key,
                    artist_key,
                    str(artist.get("artist_name", "")),
                    str(artist.get("artist_mbid", "")),
                    int(artist.get("playcount", 0)),
                    first_seen_utc,
                )
            )
        if not rows:
            return 0

        before = self.conn.total_changes
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO raw_edges
                (user_key, artist_key, artist_name, artist_mbid, playcount, first_seen_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def count_edges(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM raw_edges")
        return int(cursor.fetchone()[0])

    def close(self) -> None:
        self.conn.close()


@dataclass
class CrawlContext:
    project_root: Path
    raw_root: Path
    force_refetch_completed_pages: bool
    force_revalidate_cache: bool
    save_state_every_n_pages: int
    max_users: int
    target_raw_interactions: int
    cleaned_target: int
    cleaned_check_every_users: int
    min_user_interactions: int
    min_item_interactions: int
    raw_edges_db_path: Path
    quota_max_bytes: int
    quota_max_requests: int
    progress_log_path: Path

    def log_progress(self, payload: Dict[str, Any]) -> None:
        self.progress_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp_utc": utc_now_iso(), **payload}
        with self.progress_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def _replace_atomic(tmp: Path, out_path: Path, max_retries: int = 5) -> None:
    """Atomic rename tmp -> out_path, with retries for Windows 'file in use'."""
    for attempt in range(max_retries):
        try:
            tmp.replace(out_path)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise


def write_raw_page(
    *,
    raw_root: Path,
    method: str,
    username: str,
    page: int,
    wrapped_payload: Dict[str, Any],
) -> Path:
    method_dir = raw_root / method / safe_path_component(username)
    method_dir.mkdir(parents=True, exist_ok=True)
    out_path = method_dir / f"page_{page:05d}.json"
    if not out_path.exists():
        tmp = out_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(wrapped_payload, handle, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_atomic(tmp, out_path)
    return out_path


def add_manifest_record(
    *,
    manifest: RawManifestWriter,
    method: str,
    username: str,
    page: int,
    response_file: Path,
    api_result: Any,
    params: Dict[str, Any],
) -> None:
    record_key = f"{method}|{username}|{page}"
    payload = {
        "record_key": record_key,
        "method": method,
        "username": username,
        "page": page,
        "response_file": str(response_file),
        "status_code": api_result.status_code,
        "response_bytes": api_result.response_bytes,
        "downloaded_bytes": api_result.downloaded_bytes,
        "from_cache": api_result.from_cache,
        "api_error_code": api_result.api_error_code,
        "fetched_at_utc": api_result.fetched_at_utc,
        "cache_path": api_result.cache_path,
        "params": params,
    }
    manifest.append_once(payload)


def update_api_stats(state: CrawlState, api_result: Any) -> None:
    state.stats["api_calls"] = int(state.stats.get("api_calls", 0)) + 1
    state.stats["downloaded_bytes"] = int(state.stats.get("downloaded_bytes", 0)) + int(
        api_result.downloaded_bytes
    )


def should_stop_for_quota(state: CrawlState, ctx: CrawlContext) -> Optional[str]:
    if ctx.quota_max_bytes > 0 and state.stats.get("downloaded_bytes", 0) >= ctx.quota_max_bytes:
        return "approved_quota_max_bytes_reached"
    if ctx.quota_max_requests > 0 and state.stats.get("api_calls", 0) >= ctx.quota_max_requests:
        return "approved_quota_max_requests_reached"
    return None


def crawl_friends_pages(
    *,
    username: str,
    client: LastFMClient,
    state: CrawlState,
    state_store: ResumeStateStore,
    manifest: RawManifestWriter,
    ctx: CrawlContext,
    friends_limit: int,
) -> None:
    if username in state.users_friends_completed and not ctx.force_refetch_completed_pages:
        return

    known_total = state.friends_total_pages.get(username)
    if known_total is None:
        page1 = ctx.raw_root / "user.getFriends" / safe_path_component(username) / "page_00001.json"
        if page1.exists():
            try:
                payload = json.loads(page1.read_text(encoding="utf-8"))
                body = payload.get("payload", {})
                known_total = parse_total_pages(
                    body.get("friends", {}) if isinstance(body, dict) else {},
                    default=1,
                )
            except json.JSONDecodeError:
                known_total = 1
        else:
            known_total = 1

    page = 1
    pages_since_save = 0

    while page <= known_total:
        key = page_key(username, page)
        if key in state.friends_pages_done and not ctx.force_refetch_completed_pages:
            page += 1
            continue

        params = {"user": username, "page": page, "limit": friends_limit}
        api_result = client.request(
            method="user.getFriends",
            params=params,
            force_revalidate=ctx.force_revalidate_cache,
            force_disable_cache=False,
        )
        update_api_stats(state, api_result)

        wrapped = {
            "meta": {
                "method": "user.getFriends",
                "username": username,
                "page": page,
                "fetched_at_utc": api_result.fetched_at_utc,
                "status_code": api_result.status_code,
                "response_bytes": api_result.response_bytes,
                "downloaded_bytes": api_result.downloaded_bytes,
                "from_cache": api_result.from_cache,
                "params": params,
            },
            "payload": api_result.payload,
        }
        out_path = write_raw_page(
            raw_root=ctx.raw_root,
            method="user.getFriends",
            username=username,
            page=page,
            wrapped_payload=wrapped,
        )
        add_manifest_record(
            manifest=manifest,
            method="user.getFriends",
            username=username,
            page=page,
            response_file=out_path,
            api_result=api_result,
            params=params,
        )

        payload = api_result.payload
        known_total = parse_total_pages(payload.get("friends", {}), default=known_total)
        state.friends_total_pages[username] = known_total
        state.friends_pages_done.add(key)
        state.stats["friend_pages_saved"] = int(state.stats.get("friend_pages_saved", 0)) + 1

        for friend in extract_friend_usernames(payload):
            if len(state.seen_users) >= ctx.max_users:
                break
            if friend not in state.seen_users:
                state.seen_users.add(friend)
                state.queue.append(friend)

        quota_stop = should_stop_for_quota(state, ctx)
        if quota_stop:
            state_store.save(state)
            raise RuntimeError(quota_stop)

        page += 1
        pages_since_save += 1
        if pages_since_save >= ctx.save_state_every_n_pages:
            state_store.save(state)
            pages_since_save = 0

    state.users_friends_completed.add(username)
    state_store.save(state)


def crawl_library_pages(
    *,
    username: str,
    client: LastFMClient,
    state: CrawlState,
    state_store: ResumeStateStore,
    manifest: RawManifestWriter,
    edge_index: RawEdgeIndex,
    ctx: CrawlContext,
    library_limit: int,
) -> None:
    if username in state.users_library_completed and not ctx.force_refetch_completed_pages:
        return

    known_total = state.library_total_pages.get(username)
    if known_total is None:
        page1 = ctx.raw_root / "library.getArtists" / safe_path_component(username) / "page_00001.json"
        if page1.exists():
            try:
                payload = json.loads(page1.read_text(encoding="utf-8"))
                body = payload.get("payload", {})
                known_total = parse_total_pages(
                    body.get("artists", {}) if isinstance(body, dict) else {},
                    default=1,
                )
            except json.JSONDecodeError:
                known_total = 1
        else:
            known_total = 1

    page = 1
    pages_since_save = 0

    while page <= known_total:
        key = page_key(username, page)
        if key in state.library_pages_done and not ctx.force_refetch_completed_pages:
            page += 1
            continue

        params = {"user": username, "page": page, "limit": library_limit}
        api_result = client.request(
            method="library.getArtists",
            params=params,
            force_revalidate=ctx.force_revalidate_cache,
            force_disable_cache=False,
        )
        update_api_stats(state, api_result)

        wrapped = {
            "meta": {
                "method": "library.getArtists",
                "username": username,
                "page": page,
                "fetched_at_utc": api_result.fetched_at_utc,
                "status_code": api_result.status_code,
                "response_bytes": api_result.response_bytes,
                "downloaded_bytes": api_result.downloaded_bytes,
                "from_cache": api_result.from_cache,
                "params": params,
            },
            "payload": api_result.payload,
        }
        out_path = write_raw_page(
            raw_root=ctx.raw_root,
            method="library.getArtists",
            username=username,
            page=page,
            wrapped_payload=wrapped,
        )
        add_manifest_record(
            manifest=manifest,
            method="library.getArtists",
            username=username,
            page=page,
            response_file=out_path,
            api_result=api_result,
            params=params,
        )

        payload = api_result.payload
        known_total = parse_total_pages(payload.get("artists", {}), default=known_total)
        state.library_total_pages[username] = known_total
        state.library_pages_done.add(key)
        state.stats["library_pages_saved"] = int(state.stats.get("library_pages_saved", 0)) + 1

        artists = extract_artists(payload)
        edge_index.add_edges(username, artists, api_result.fetched_at_utc)

        quota_stop = should_stop_for_quota(state, ctx)
        if quota_stop:
            state_store.save(state)
            raise RuntimeError(quota_stop)

        page += 1
        pages_since_save += 1
        if pages_since_save >= ctx.save_state_every_n_pages:
            state_store.save(state)
            pages_since_save = 0

    state.users_library_completed.add(username)
    state.stats["users_completed"] = int(state.stats.get("users_completed", 0)) + 1
    state_store.save(state)


def should_stop_for_target(
    *,
    edge_count: int,
    target_raw_interactions: int,
    cleaned_target: int,
    cleaned_estimate: int,
) -> Optional[str]:
    if edge_count >= target_raw_interactions:
        return "target_raw_interactions_reached"
    if cleaned_target > 0 and cleaned_estimate >= cleaned_target:
        return "cleaned_target_reached"
    return None


def estimate_cleaned_edges(
    *,
    raw_edges_db_path: Path,
    min_user_interactions: int,
    min_item_interactions: int,
) -> int:
    conn = sqlite3.connect(raw_edges_db_path)
    try:
        df = pd.read_sql_query("SELECT user_key, artist_key FROM raw_edges", conn)
    finally:
        conn.close()

    if df.empty:
        return 0

    filtered = iterative_kcore_filter(
        df=df,
        user_col="user_key",
        item_col="artist_key",
        min_user_interactions=min_user_interactions,
        min_item_interactions=min_item_interactions,
    )
    return int(len(filtered))


def assert_legal_gate(
    *,
    config: Dict[str, Any],
    project_root: Path,
    target_raw_interactions: int,
) -> None:
    legal_cfg = config.get("legal", {})
    crawl_cfg = config.get("crawl", {})
    require_gate = bool(legal_cfg.get("require_clearance_for_full_crawl", True))
    pilot_ceiling = int(crawl_cfg.get("pilot_mode_max_target_raw", 300000))
    if not require_gate or target_raw_interactions <= pilot_ceiling:
        return

    clearance_file = resolve_path(project_root, str(legal_cfg.get("clearance_file", "")))
    if not clearance_file.exists():
        raise RuntimeError(
            f"Legal gate blocked full crawl. Missing clearance file: {clearance_file}"
        )
    with clearance_file.open("r", encoding="utf-8") as handle:
        clearance = json.load(handle)
    if not bool(clearance.get("approved", False)):
        raise RuntimeError(
            "Legal gate blocked full crawl. Set approved=true in legal clearance after approval."
        )


def run_crawl(config_path: Path, seeds_path: Path, target_raw_interactions: int) -> None:
    config = read_yaml(config_path)
    project_root = config_path.resolve().parents[1]

    assert_legal_gate(
        config=config,
        project_root=project_root,
        target_raw_interactions=target_raw_interactions,
    )

    api_cfg = config.get("api", {})
    crawl_cfg = config.get("crawl", {})
    legal_cfg = config.get("legal", {})

    api_key_env = str(api_cfg.get("api_key_env", "LASTFM_API_KEY"))
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        api_key_file = api_cfg.get("api_key_file")
        if api_key_file:
            key_path = resolve_path(project_root, api_key_file)
            if key_path.exists():
                api_key = key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError(
            f"Missing Last.fm API key. Set env {api_key_env} or create config/api_key.txt with your key. "
            "Get a key at https://www.last.fm/api/account/create"
        )

    raw_root = resolve_path(project_root, "data/raw_api")
    raw_root.mkdir(parents=True, exist_ok=True)

    state_path = resolve_path(project_root, str(crawl_cfg.get("resume_state_path")))
    manifest_path = resolve_path(project_root, str(crawl_cfg.get("raw_manifest_path")))
    raw_edges_db_path = resolve_path(project_root, str(crawl_cfg.get("raw_edges_index_db")))
    api_call_log_path = resolve_path(project_root, str(crawl_cfg.get("api_call_log_path")))
    progress_log_path = resolve_path(project_root, str(crawl_cfg.get("crawl_progress_log_path")))

    seeds = read_seed_users(seeds_path)
    if not seeds:
        raise RuntimeError(f"No seed users found in {seeds_path}")

    state_store = ResumeStateStore(state_path)
    state = state_store.load_or_initialize(seeds)

    manifest = RawManifestWriter(manifest_path)
    edge_index = RawEdgeIndex(raw_edges_db_path)

    max_users = int(crawl_cfg.get("max_users", 20000))
    cleaned_target = int(crawl_cfg.get("stop_after_cleaned_edges", 0))
    clean_cfg = config.get("clean", {})

    ctx = CrawlContext(
        project_root=project_root,
        raw_root=raw_root,
        force_refetch_completed_pages=bool(crawl_cfg.get("force_refetch_completed_pages", False)),
        force_revalidate_cache=bool(crawl_cfg.get("force_revalidate_cache", False)),
        save_state_every_n_pages=int(crawl_cfg.get("save_state_every_n_pages", 5)),
        max_users=max_users,
        target_raw_interactions=target_raw_interactions,
        cleaned_target=cleaned_target,
        cleaned_check_every_users=int(crawl_cfg.get("cleaned_edge_check_every_users", 100)),
        min_user_interactions=int(clean_cfg.get("min_user_interactions", 10)),
        min_item_interactions=int(clean_cfg.get("min_item_interactions", 5)),
        raw_edges_db_path=raw_edges_db_path,
        quota_max_bytes=int(legal_cfg.get("approved_quota_max_bytes", 0) or 0),
        quota_max_requests=int(legal_cfg.get("approved_quota_max_requests", 0) or 0),
        progress_log_path=progress_log_path,
    )

    client = LastFMClient(
        api_key=api_key,
        base_url=str(api_cfg.get("base_url")),
        user_agent=str(api_cfg.get("user_agent", "phase2_lastfm/1.0")),
        timeout_seconds=int(api_cfg.get("timeout_seconds", 30)),
        rate_limit_rps=float(api_cfg.get("rate_limit_rps", 1.0)),
        max_retries=int(api_cfg.get("max_retries", 6)),
        backoff_initial_seconds=float(api_cfg.get("backoff_initial_seconds", 1.0)),
        backoff_max_seconds=float(api_cfg.get("backoff_max_seconds", 120.0)),
        jitter_seconds=float(api_cfg.get("jitter_seconds", 0.3)),
        retryable_http_statuses=list(api_cfg.get("retryable_http_statuses", [429, 500, 502, 503])),
        retryable_api_error_codes=list(api_cfg.get("retryable_api_error_codes", [11, 16, 29])),
        cache_root=raw_root / "http_cache",
        api_call_log_path=api_call_log_path,
    )

    stop_reason: Optional[str] = None
    cleaned_estimate_latest = 0
    try:
        while state.queue:
            edge_count = edge_index.count_edges()
            stop_reason = should_stop_for_target(
                edge_count=edge_count,
                target_raw_interactions=target_raw_interactions,
                cleaned_target=cleaned_target,
                cleaned_estimate=cleaned_estimate_latest,
            )
            if stop_reason:
                break

            quota_stop = should_stop_for_quota(state, ctx)
            if quota_stop:
                stop_reason = quota_stop
                break

            if len(state.seen_users) >= max_users and not state.queue:
                stop_reason = "max_users_reached"
                break

            username = state.queue[0]

            if (
                username in state.users_friends_completed
                and username in state.users_library_completed
                and not ctx.force_refetch_completed_pages
            ):
                state.queue.popleft()
                continue

            try:
                crawl_friends_pages(
                    username=username,
                    client=client,
                    state=state,
                    state_store=state_store,
                    manifest=manifest,
                    ctx=ctx,
                    friends_limit=int(crawl_cfg.get("friends_limit", 200)),
                )

                crawl_library_pages(
                    username=username,
                    client=client,
                    state=state,
                    state_store=state_store,
                    manifest=manifest,
                    edge_index=edge_index,
                    ctx=ctx,
                    library_limit=int(crawl_cfg.get("library_limit", 200)),
                )
            except LastFMClientError as user_exc:
                # Fail fast on invalid API key (Last.fm error 10) so user can fix env
                if isinstance(user_exc, LastFMAPIError) and getattr(user_exc, "error_code", None) == 10:
                    raise RuntimeError(
                        "Last.fm API key invalid (error 10). "
                        "Get a key at https://www.last.fm/api/account/create and set: "
                        f"$env:LASTFM_API_KEY=\"your_key\" (PowerShell) or export LASTFM_API_KEY=your_key (bash)"
                    ) from user_exc
                state.queue.popleft()
                state_store.save(state)
                ctx.log_progress(
                    {
                        "event": "user_skipped_after_error",
                        "username": username,
                        "error": str(user_exc),
                        "queue_size": len(state.queue),
                    }
                )
                continue

            state.queue.popleft()
            state_store.save(state)

            edge_count = edge_index.count_edges()
            completed_users = int(state.stats.get("users_completed", 0))
            if (
                cleaned_target > 0
                and completed_users > 0
                and completed_users % max(ctx.cleaned_check_every_users, 1) == 0
            ):
                cleaned_estimate_latest = estimate_cleaned_edges(
                    raw_edges_db_path=ctx.raw_edges_db_path,
                    min_user_interactions=ctx.min_user_interactions,
                    min_item_interactions=ctx.min_item_interactions,
                )

            ctx.log_progress(
                {
                    "username": username,
                    "queue_size": len(state.queue),
                    "seen_users": len(state.seen_users),
                    "users_completed": len(state.users_library_completed),
                    "raw_unique_edges": edge_count,
                    "cleaned_edge_estimate": cleaned_estimate_latest,
                    "api_calls": state.stats.get("api_calls", 0),
                    "downloaded_bytes": state.stats.get("downloaded_bytes", 0),
                }
            )

            stop_reason = should_stop_for_target(
                edge_count=edge_count,
                target_raw_interactions=target_raw_interactions,
                cleaned_target=cleaned_target,
                cleaned_estimate=cleaned_estimate_latest,
            )
            if stop_reason:
                break

        if stop_reason is None:
            stop_reason = "queue_exhausted"

    except LastFMClientError as exc:
        stop_reason = f"client_error:{exc}"
    except RuntimeError as exc:
        stop_reason = str(exc)
    finally:
        state_store.save(state)
        edge_count = edge_index.count_edges()
        summary = {
            "finished_at_utc": utc_now_iso(),
            "stop_reason": stop_reason,
            "queue_size": len(state.queue),
            "seen_users": len(state.seen_users),
            "users_library_completed": len(state.users_library_completed),
            "users_friends_completed": len(state.users_friends_completed),
            "raw_unique_edges": edge_count,
            "cleaned_edge_estimate_latest": cleaned_estimate_latest,
            "stats": state.stats,
            "target_raw_interactions": target_raw_interactions,
        }
        summary_path = raw_root / "crawl_summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=True, indent=2)
        ctx.log_progress({"event": "crawl_finished", **summary})
        edge_index.close()
        client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BFS crawl using Last.fm user.getFriends + library.getArtists"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    parser.add_argument("--seeds", required=True, help="Seed usernames file.")
    parser.add_argument(
        "--target-raw-interactions",
        required=True,
        type=int,
        help="Stop when raw unique user-artist edges reaches this target.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    seeds_path = Path(args.seeds).resolve()
    run_crawl(
        config_path=config_path,
        seeds_path=seeds_path,
        target_raw_interactions=int(args.target_raw_interactions),
    )


if __name__ == "__main__":
    main()
