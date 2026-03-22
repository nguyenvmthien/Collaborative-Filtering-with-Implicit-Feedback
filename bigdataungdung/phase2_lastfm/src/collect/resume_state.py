import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, Iterable, Set


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def page_key(username: str, page: int) -> str:
    return f"{username}\t{page}"


@dataclass
class CrawlState:
    queue: Deque[str] = field(default_factory=deque)
    seen_users: Set[str] = field(default_factory=set)
    friends_pages_done: Set[str] = field(default_factory=set)
    library_pages_done: Set[str] = field(default_factory=set)
    friends_total_pages: Dict[str, int] = field(default_factory=dict)
    library_total_pages: Dict[str, int] = field(default_factory=dict)
    users_friends_completed: Set[str] = field(default_factory=set)
    users_library_completed: Set[str] = field(default_factory=set)
    stats: Dict[str, int] = field(
        default_factory=lambda: {
            "api_calls": 0,
            "downloaded_bytes": 0,
            "friend_pages_saved": 0,
            "library_pages_saved": 0,
            "users_completed": 0,
        }
    )
    last_update_utc: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_seeds(cls, seeds: Iterable[str]) -> "CrawlState":
        deduped = []
        seen = set()
        for user in seeds:
            if user and user not in seen:
                seen.add(user)
                deduped.append(user)
        return cls(queue=deque(deduped), seen_users=seen)

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "queue": list(self.queue),
            "seen_users": sorted(self.seen_users),
            "friends_pages_done": sorted(self.friends_pages_done),
            "library_pages_done": sorted(self.library_pages_done),
            "friends_total_pages": self.friends_total_pages,
            "library_total_pages": self.library_total_pages,
            "users_friends_completed": sorted(self.users_friends_completed),
            "users_library_completed": sorted(self.users_library_completed),
            "stats": self.stats,
            "last_update_utc": self.last_update_utc,
        }

    @classmethod
    def from_json_dict(cls, payload: Dict[str, object]) -> "CrawlState":
        state = cls()
        state.queue = deque(payload.get("queue", []))
        state.seen_users = set(payload.get("seen_users", []))
        state.friends_pages_done = set(payload.get("friends_pages_done", []))
        state.library_pages_done = set(payload.get("library_pages_done", []))
        state.friends_total_pages = {
            str(k): int(v) for k, v in dict(payload.get("friends_total_pages", {})).items()
        }
        state.library_total_pages = {
            str(k): int(v) for k, v in dict(payload.get("library_total_pages", {})).items()
        }
        state.users_friends_completed = set(payload.get("users_friends_completed", []))
        state.users_library_completed = set(payload.get("users_library_completed", []))
        state.stats = dict(payload.get("stats", {}))
        state.last_update_utc = str(payload.get("last_update_utc", utc_now_iso()))
        return state


class ResumeStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_or_initialize(self, seeds: Iterable[str]) -> CrawlState:
        if not self.state_path.exists():
            return CrawlState.from_seeds(seeds)

        with self.state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return CrawlState.from_json_dict(payload)

    def save(self, state: CrawlState) -> None:
        state.last_update_utc = utc_now_iso()
        tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(state.to_json_dict(), handle, ensure_ascii=True, indent=2)
        tmp_path.replace(self.state_path)
