"""Export the database to the static JSON the dashboard reads, and assemble _site."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, normalize, store

SCHEMA_VERSION = 1

ITEM_FIELDS = (
    "id", "name", "url", "homepage", "description", "summary", "category",
    "tags", "license", "license_open", "stars", "forks", "open_issues",
    "language", "topics", "pushed_at", "created_at", "archived", "points",
    "comments", "discussion_url", "kind", "sources", "self_hostable",
    "maturity", "target_user", "difficulty", "free_tier_notes", "score",
    "score_parts", "first_seen", "last_seen", "enriched_at", "enrichment_model",
)


def slim(item: Dict[str, Any]) -> Dict[str, Any]:
    out = {field: item.get(field) for field in ITEM_FIELDS}
    out["tags"] = out.get("tags") or []
    out["topics"] = out.get("topics") or []
    out["sources"] = out.get("sources") or []
    if out.get("description") and len(out["description"]) > 400:
        out["description"] = out["description"][:397] + "..."
    return out


def _facet(items: List[Dict[str, Any]], field: str, limit: int = 40) -> List[Dict[str, Any]]:
    counter: Counter = Counter()
    for item in items:
        value = item.get(field)
        if isinstance(value, list):
            for entry in value:
                if entry:
                    counter[str(entry)] += 1
        elif value:
            counter[str(value)] += 1
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(limit)
    ]


def build_payload(conn, generated_at: Optional[str] = None) -> Dict[str, Any]:
    items = store.all_items(conn)
    stats = {
        "total": len(items),
        "open_source": sum(1 for item in items if item.get("license_open")),
        "self_hostable": sum(1 for item in items if item.get("self_hostable")),
        "archived": sum(1 for item in items if item.get("archived")),
        "enriched": sum(1 for item in items if item.get("enriched_at")),
        "repos": sum(1 for item in items if item.get("kind") == "repo"),
        "news": sum(1 for item in items if item.get("kind") == "news"),
        "with_discussion": sum(1 for item in items if item.get("discussion_url")),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or store.utcnow(),
        "stats": stats,
        "facets": {
            "category": _facet(items, "category"),
            "license": _facet(items, "license"),
            "language": _facet(items, "language"),
            "kind": _facet(items, "kind"),
            "source": _facet(items, "sources"),
            "maturity": _facet(items, "maturity"),
            "target_user": _facet(items, "target_user"),
            "tags": _facet(items, "tags", limit=60),
        },
        "items": [slim(item) for item in items],
    }
    return payload


def write_index_json(conn, path: Optional[Path] = None) -> Path:
    target = Path(path) if path else config.index_json_path()
    payload = build_payload(conn)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return target


def build_site(conn=None, site_path: Optional[Path] = None) -> Path:
    """Copy web/ plus the exported data into a deployable static directory.

    The database wins when it holds items. When it is empty - the usual case on
    a CI runner, where the SQLite file is ignored and rebuildable - the
    committed data/index.json is published instead, so the deployed dashboard
    still shows the real dataset.
    """
    target = Path(site_path) if site_path else config.site_dir()
    web = config.web_dir()
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(web.iterdir()):
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)
    data_target = target / "data"
    data_target.mkdir(parents=True, exist_ok=True)
    source = config.index_json_path()
    if conn is not None and store.all_items(conn):
        write_index_json(conn, data_target / "index.json")
    elif source.exists():
        shutil.copy2(source, data_target / "index.json")
    (target / ".nojekyll").write_text("", encoding="utf-8")
    return target
