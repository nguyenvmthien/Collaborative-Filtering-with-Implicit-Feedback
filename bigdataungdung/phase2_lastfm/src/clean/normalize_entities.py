import re
from typing import Optional


_SPACE_RE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip())


def normalize_username(username: str) -> str:
    if username is None:
        return ""
    return normalize_whitespace(str(username)).lower()


def normalize_artist_name(artist_name: str) -> str:
    if artist_name is None:
        return ""
    return normalize_whitespace(str(artist_name)).lower()


def normalize_mbid(mbid: Optional[str]) -> str:
    if mbid is None:
        return ""
    return normalize_whitespace(str(mbid)).lower()


def canonical_artist_key(artist_name: str, mbid: Optional[str]) -> str:
    mbid_norm = normalize_mbid(mbid)
    if mbid_norm:
        return f"mbid:{mbid_norm}"
    name_norm = normalize_artist_name(artist_name)
    if not name_norm:
        return ""
    return f"name:{name_norm}"


def parse_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
