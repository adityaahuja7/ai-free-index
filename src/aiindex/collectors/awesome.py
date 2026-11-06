"""Curated awesome-list collector.

Curated lists are the highest-signal source for "free and actually usable" AI
software. Links that point at GitHub repositories reuse the 'gh:owner/repo' id,
so they merge with the GitHub collector's data and simply add the 'curated'
source plus a human-written description.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..http import get_text
from ..normalize import LINK_RE, canonical_url, github_slug


def fetch_readme(slug: str) -> Optional[str]:
    """Try main, then master. Lists are cheap and cached by the CDN."""
    for branch in ("main", "master"):
        url = "https://raw.githubusercontent.com/%s/%s/README.md" % (slug, branch)
        try:
            text = get_text(url, retries=1)
        except Exception:
            continue
        if text:
            return text
    return None


def parse_markdown(text: str, source_list: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set = set()
    for line in text.splitlines():
        match = LINK_RE.match(line)
        if not match:
            continue
        name, url, description = match.group(1).strip(), match.group(2).strip(), (match.group(3) or "").strip()
        if not name or not url:
            continue
        slug = github_slug(url)
        if slug:
            item_id = "gh:%s" % slug
            item_url = "https://github.com/%s" % slug
        elif canonical_url(url).startswith("github.com/"):
            continue  # topics pages, orgs, sponsors... not a project
        else:
            item_id = "web:%s" % url
            item_url = url
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append(
            {
                "id": item_id,
                "source": "awesome",
                "sources": ["awesome"],
                "kind": "repo" if slug else "curated",
                "name": name[:120],
                "url": item_url,
                "description": description[:400],
                "topics": [],
                "curated_by": source_list,
                "raw": {"curated_by": source_list},
            }
        )
    return items


def collect(cfg: Dict[str, Any], log=print) -> List[Dict[str, Any]]:
    if not cfg or cfg.get("enabled") is False:
        return []
    lists: List[str] = list(cfg.get("lists") or [])
    delay = float(cfg.get("request_delay_seconds", 1.0))
    items: List[Dict[str, Any]] = []
    for slug in lists:
        log("  awesome list: %s" % slug)
        text = fetch_readme(slug)
        if not text:
            log("  awesome list: could not fetch %s" % slug)
            continue
        found = parse_markdown(text, slug)
        log("  awesome list: %s -> %d entries" % (slug, len(found)))
        items.extend(found)
        time.sleep(delay)
    log("  awesome: %d entries" % len(items))
    return items
