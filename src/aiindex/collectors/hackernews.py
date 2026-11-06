"""Hacker News (Algolia) collector: shows what the community is talking about.

Stories that point at a repository already in the index are merged into that
repository by the normaliser (as a 'hackernews' source plus a discussion link),
so news never creates a duplicate card for a known project.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ..http import get_json

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"


def normalize(hit: Dict[str, Any]) -> Dict[str, Any]:
    object_id = str(hit.get("objectID") or "")
    story_url = hit.get("url") or "https://news.ycombinator.com/item?id=%s" % object_id
    title = (hit.get("title") or "").strip()
    return {
        "id": "hn:%s" % object_id,
        "source": "hackernews",
        "sources": ["hackernews"],
        "kind": "news",
        "name": title,
        "url": story_url,
        "homepage": "",
        "description": (hit.get("story_text") or "")[:400],
        "points": hit.get("points") or 0,
        "comments": hit.get("num_comments") or 0,
        "created_at": hit.get("created_at") or "",
        "discussion_url": "https://news.ycombinator.com/item?id=%s" % object_id,
        "topics": [],
        "raw": {"author": hit.get("author"), "story_id": object_id},
    }


def collect(cfg: Dict[str, Any], log=print) -> List[Dict[str, Any]]:
    if not cfg or cfg.get("enabled") is False:
        return []
    queries: List[str] = list(cfg.get("queries") or [])
    if not queries:
        return []
    hits_per_page = int(cfg.get("hits_per_page", 100))
    min_points = int(cfg.get("min_points", 25))
    days = int(cfg.get("days", 45))
    delay = float(cfg.get("request_delay_seconds", 1.0))
    cutoff = int(time.time()) - days * 86400
    items: List[Dict[str, Any]] = []
    seen: set = set()
    for query in queries:
        log("  hackernews search: %s" % query)
        try:
            payload = get_json(
                SEARCH_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": hits_per_page,
                    "numericFilters": "points>%d,created_at_i>%d" % (min_points, cutoff),
                },
                retries=2,
            )
        except Exception as exc:
            log("  hackernews: query failed (%s)" % exc)
            continue
        for hit in (payload or {}).get("hits", []) or []:
            item = normalize(hit)
            if not item["name"] or item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)
        time.sleep(delay)
    log("  hackernews: %d stories" % len(items))
    return items
