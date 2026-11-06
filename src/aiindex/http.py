"""Tiny HTTP helpers built on urllib, with retries and polite backoff.

No third-party dependencies: the whole pipeline must run on a free runner.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Optional, Tuple

USER_AGENT = "ai-free-index/0.1 (+https://github.com/; free-software indexer)"


class HttpError(RuntimeError):
    """Raised when a request keeps failing after the configured retries."""

    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def build_url(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None}
    if not clean:
        return url
    joiner = "&" if "?" in url else "?"
    return url + joiner + urllib.parse.urlencode(clean, doseq=True)


def request_text(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 2.0,
    retry_statuses: Iterable[int] = (403, 429, 500, 502, 503, 504),
    allow_404: bool = True,
    method: str = "GET",
    data: Optional[bytes] = None,
) -> Optional[str]:
    """Fetch a URL as text. Returns None for 404 when allow_404 is set."""
    full_url = build_url(url, params)
    attempt = 0
    last_error: Optional[Exception] = None
    while attempt <= retries:
        req = urllib.request.Request(full_url, method=method, data=data)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json, text/plain, */*")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:  # pragma: no cover - defensive
                body = ""
            if exc.code == 404 and allow_404:
                return None
            if exc.code in set(retry_statuses) and attempt < retries:
                wait = backoff * (2 ** attempt)
                last_error = HttpError("HTTP %s on %s" % (exc.code, full_url), exc.code, body)
                time.sleep(wait)
                attempt += 1
                continue
            raise HttpError("HTTP %s on %s" % (exc.code, full_url), exc.code, body)
        except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                attempt += 1
                continue
            raise HttpError("Network failure on %s: %s" % (full_url, exc))
    raise HttpError("Exhausted retries for %s: %s" % (full_url, last_error))


def get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> Any:
    text = request_text(url, params=params, headers=headers, **kwargs)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError("Invalid JSON from %s: %s" % (url, exc))


def get_text(url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[str]:
    return request_text(url, params=params, **kwargs)


def post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 120,
    retries: int = 2,
    backoff: float = 4.0,
) -> Tuple[Optional[Any], Optional[int], str]:
    """POST JSON and return (parsed_body, status, raw_text).

    Unlike get_json this does not raise on HTTP errors: callers need the status
    code to implement key rotation and quota backoff.
    """
    body = json.dumps(payload).encode("utf-8")
    full_headers = {"Content-Type": "application/json"}
    full_headers.update(headers or {})
    attempt = 0
    while attempt <= retries:
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("User-Agent", USER_AGENT)
        for key, value in full_headers.items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                try:
                    return json.loads(raw), response.status, raw
                except json.JSONDecodeError:
                    return None, response.status, raw
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            raw = ""
            try:
                raw = exc.read().decode("utf-8", "replace")
            except Exception:  # pragma: no cover - defensive
                raw = ""
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                attempt += 1
                continue
            return None, exc.code, raw
        except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                attempt += 1
                continue
            return None, None, str(exc)
    return None, None, "exhausted retries"
