import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LastFMClientError(RuntimeError):
    pass


class LastFMAPIError(LastFMClientError):
    def __init__(self, error_code: int, message: str) -> None:
        super().__init__(f"Last.fm API error {error_code}: {message}")
        self.error_code = error_code
        self.message = message


@dataclass
class RequestResult:
    payload: Dict[str, Any]
    status_code: int
    response_bytes: int
    downloaded_bytes: int
    from_cache: bool
    fetched_at_utc: str
    cache_path: str
    api_error_code: Optional[int]
    api_error_message: Optional[str]
    duration_ms: int


class LastFMClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        user_agent: str,
        timeout_seconds: int,
        rate_limit_rps: float,
        max_retries: int,
        backoff_initial_seconds: float,
        backoff_max_seconds: float,
        jitter_seconds: float,
        retryable_http_statuses: list[int],
        retryable_api_error_codes: list[int],
        cache_root: Path,
        api_call_log_path: Path,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.rate_limit_rps = max(rate_limit_rps, 0.0)
        self.max_retries = max_retries
        self.backoff_initial_seconds = backoff_initial_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.jitter_seconds = jitter_seconds
        self.retryable_http_statuses = set(retryable_http_statuses)
        self.retryable_api_error_codes = set(retryable_api_error_codes)
        self.cache_root = cache_root
        self.api_call_log_path = api_call_log_path

        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.api_call_log_path.parent.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._last_request_ts = 0.0

    def close(self) -> None:
        self.session.close()

    def _sleep_for_rate_limit(self) -> None:
        if self.rate_limit_rps <= 0:
            return
        min_interval = 1.0 / self.rate_limit_rps
        now = time.monotonic()
        wait = min_interval - (now - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    @staticmethod
    def _canonical_params(params: Dict[str, Any]) -> Dict[str, str]:
        return {str(k): str(v) for k, v in sorted(params.items(), key=lambda kv: kv[0])}

    def _cache_path(self, method: str, params: Dict[str, Any]) -> Path:
        canonical = {"method": method, **self._canonical_params(params)}
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha1(canonical_json.encode("utf-8")).hexdigest()
        method_dir = self.cache_root / method
        method_dir.mkdir(parents=True, exist_ok=True)
        return method_dir / f"{digest}.json"

    def _read_cache(self, cache_path: Path) -> Optional[Dict[str, Any]]:
        if not cache_path.exists():
            return None
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_cache(
        self,
        *,
        cache_path: Path,
        method: str,
        params: Dict[str, Any],
        status_code: int,
        response_headers: Dict[str, str],
        payload: Dict[str, Any],
        response_bytes: int,
    ) -> None:
        wrapped = {
            "method": method,
            "params": self._canonical_params(params),
            "status_code": status_code,
            "fetched_at_utc": utc_now_iso(),
            "response_headers": response_headers,
            "response_bytes": response_bytes,
            "payload": payload,
        }
        tmp = cache_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(wrapped, handle, ensure_ascii=True)
        tmp.replace(cache_path)

    def _log_api_call(
        self,
        *,
        method: str,
        params: Dict[str, Any],
        status_code: int,
        response_bytes: int,
        downloaded_bytes: int,
        from_cache: bool,
        attempt: int,
        duration_ms: int,
        api_error_code: Optional[int],
    ) -> None:
        entry = {
            "timestamp_utc": utc_now_iso(),
            "method": method,
            "params": self._canonical_params(params),
            "status_code": status_code,
            "response_bytes": int(response_bytes),
            "downloaded_bytes": int(downloaded_bytes),
            "from_cache": bool(from_cache),
            "attempt": int(attempt),
            "duration_ms": int(duration_ms),
            "api_error_code": api_error_code,
        }
        with self.api_call_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def _backoff_sleep(self, attempt: int, api_error_code: Optional[int]) -> None:
        base_delay = self.backoff_initial_seconds * (2 ** max(attempt - 1, 0))
        delay = min(base_delay, self.backoff_max_seconds)
        if api_error_code == 29:
            delay = max(delay, 5.0)
        delay += random.uniform(0.0, self.jitter_seconds)
        time.sleep(delay)

    def request(
        self,
        *,
        method: str,
        params: Dict[str, Any],
        force_revalidate: bool = False,
        force_disable_cache: bool = False,
    ) -> RequestResult:
        clean_params = dict(params)
        cache_path = self._cache_path(method, clean_params)
        cached = self._read_cache(cache_path)

        if cached and not force_revalidate and not force_disable_cache:
            payload = dict(cached.get("payload", {}))
            response_bytes = int(cached.get("response_bytes", 0))
            self._log_api_call(
                method=method,
                params=clean_params,
                status_code=int(cached.get("status_code", 200)),
                response_bytes=response_bytes,
                downloaded_bytes=0,
                from_cache=True,
                attempt=0,
                duration_ms=0,
                api_error_code=None,
            )
            return RequestResult(
                payload=payload,
                status_code=int(cached.get("status_code", 200)),
                response_bytes=response_bytes,
                downloaded_bytes=0,
                from_cache=True,
                fetched_at_utc=str(cached.get("fetched_at_utc", utc_now_iso())),
                cache_path=str(cache_path),
                api_error_code=None,
                api_error_message=None,
                duration_ms=0,
            )

        request_params = {
            **clean_params,
            "method": method,
            "api_key": self.api_key,
            "format": "json",
        }

        conditional_headers: Dict[str, str] = {}
        if force_revalidate and cached:
            headers = dict(cached.get("response_headers", {}))
            etag = headers.get("ETag")
            last_modified = headers.get("Last-Modified")
            if etag:
                conditional_headers["If-None-Match"] = etag
            if last_modified:
                conditional_headers["If-Modified-Since"] = last_modified

        for attempt in range(1, self.max_retries + 2):
            self._sleep_for_rate_limit()
            start = time.monotonic()
            try:
                response = self.session.get(
                    self.base_url,
                    params=request_params,
                    headers=conditional_headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                self._log_api_call(
                    method=method,
                    params=clean_params,
                    status_code=-1,
                    response_bytes=0,
                    downloaded_bytes=0,
                    from_cache=False,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    api_error_code=None,
                )
                if attempt <= self.max_retries:
                    self._backoff_sleep(attempt, None)
                    continue
                raise LastFMClientError(f"Request failed for {method}: {exc}") from exc

            duration_ms = int((time.monotonic() - start) * 1000)
            status_code = int(response.status_code)
            response_bytes = len(response.content or b"")
            downloaded_bytes = response_bytes

            if status_code == 304 and cached:
                payload = dict(cached.get("payload", {}))
                self._log_api_call(
                    method=method,
                    params=clean_params,
                    status_code=status_code,
                    response_bytes=response_bytes,
                    downloaded_bytes=downloaded_bytes,
                    from_cache=True,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    api_error_code=None,
                )
                return RequestResult(
                    payload=payload,
                    status_code=status_code,
                    response_bytes=int(cached.get("response_bytes", 0)),
                    downloaded_bytes=downloaded_bytes,
                    from_cache=True,
                    fetched_at_utc=str(cached.get("fetched_at_utc", utc_now_iso())),
                    cache_path=str(cache_path),
                    api_error_code=None,
                    api_error_message=None,
                    duration_ms=duration_ms,
                )

            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    payload = {}
            except ValueError:
                payload = {}

            error_code = payload.get("error")
            api_error_code = None
            api_error_message = None
            if error_code is not None:
                try:
                    api_error_code = int(error_code)
                except (TypeError, ValueError):
                    api_error_code = None
                api_error_message = str(payload.get("message", "unknown error"))

            is_success = status_code == 200 and api_error_code is None
            is_retryable = (
                status_code in self.retryable_http_statuses
                or (api_error_code is not None and api_error_code in self.retryable_api_error_codes)
            )

            self._log_api_call(
                method=method,
                params=clean_params,
                status_code=status_code,
                response_bytes=response_bytes,
                downloaded_bytes=downloaded_bytes,
                from_cache=False,
                attempt=attempt,
                duration_ms=duration_ms,
                api_error_code=api_error_code,
            )

            if is_success:
                self._write_cache(
                    cache_path=cache_path,
                    method=method,
                    params=clean_params,
                    status_code=status_code,
                    response_headers=dict(response.headers),
                    payload=payload,
                    response_bytes=response_bytes,
                )
                return RequestResult(
                    payload=payload,
                    status_code=status_code,
                    response_bytes=response_bytes,
                    downloaded_bytes=downloaded_bytes,
                    from_cache=False,
                    fetched_at_utc=utc_now_iso(),
                    cache_path=str(cache_path),
                    api_error_code=None,
                    api_error_message=None,
                    duration_ms=duration_ms,
                )

            if is_retryable and attempt <= self.max_retries:
                self._backoff_sleep(attempt, api_error_code)
                continue

            if api_error_code is not None:
                raise LastFMAPIError(api_error_code, api_error_message or "unknown error")
            raise LastFMClientError(f"HTTP {status_code} for {method}")

        raise LastFMClientError(f"Exceeded retries for {method}")
