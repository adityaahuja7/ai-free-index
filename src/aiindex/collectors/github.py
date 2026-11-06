"""GitHub repository search: the backbone of the index.

Uses the public REST search API. Unauthenticated access is allowed but limited to
10 searches/minute, so the collector paces itself and can use GITHUB_TOKEN when
one is available (30 searches/minute, and required in GitHub Actions anyway to
avoid shared-runner throttling).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .. import config
from ..http import get_json

SEARCH_URL = "https://api.github.com/search/repositories"


def _headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = config.github_token()
    if token:
        headers["Authorization"] = "Bearer %s" % token
    return headers


def normalize(repo: Dict[str, Any]) -> Dict[str, Any]:
    license_info = repo.get("license") or {}
    return {
        "id": "gh:%s" % repo.get("full_name", ""),
        "source": "github",
        "sources": ["github"],
        "kind": "repo",
        "name": repo.get("full_name") or "",
        "url": repo.get("html_url") or "",
        "homepage": (repo.get("homepage") or "").strip(),
        "description": (repo.get("description") or "").strip(),
        "license": license_info.get("spdx_id") or "",
        "stars": repo.get("stargazers_count") or 0,
        "forks": repo.get("forks_count") or 0,
        "open_issues": repo.get("open_issues_count") or 0,
        "language": repo.get("language") or "",
        "topics": repo.get("topics") or [],
        "pushed_at": repo.get("pushed_at") or "",
        "created_at": repo.get("created_at") or "",
        "archived": bool(repo.get("archived")),
        "raw": {
            "github_id": repo.get("id"),
            "watchers": repo.get("watchers_count"),
            "size_kb": repo.get("size"),
            "default_branch": repo.get("default_branch"),
            "is_fork": repo.get("fork"),
        },
    }


def collect(cfg: Dict[str, Any], log=print) -> List[Dict[str, Any]]:
    if not cfg or cfg.get("enabled") is False:
        return []
    queries: List[str] = list(cfg.get("queries") or [])
    if not queries:
        return []
    per_page = int(cfg.get("per_page", 100))
    min_stars = int(cfg.get("min_stars", 150))
    token = config.github_token()
    delay = float(cfg.get("request_delay_seconds") or (2.0 if token else 7.0))
    max_requests = int(cfg.get("max_requests") or len(queries))
    items: List[Dict[str, Any]] = []
    seen: set = set()
    used = 0
    for query in queries:
        if used >= max_requests:
            log("  github: request budget reached (%d)" % max_requests)
            break
        full_query = query if "stars:" in query else "%s stars:>=%d" % (query, min_stars)
        log("  github search: %s" % full_query)
        try:
            payload = get_json(
                SEARCH_URL,
                params={
                    "q": full_query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": per_page,
                },
                headers=_headers(),
                retries=2,
            )
        except Exception as exc:  # one bad query must not kill the run
            log("  github: query failed (%s)" % exc)
            used += 1
            continue
        used += 1
        for repo in (payload or {}).get("items", []) or []:
            item = normalize(repo)
            if not item["url"] or item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)
        if used < max_requests:
            time.sleep(delay)
    log("  github: %d repositories" % len(items))
    return items
