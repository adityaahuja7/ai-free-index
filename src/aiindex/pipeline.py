"""The pipeline: collect -> normalise -> score -> store -> enrich -> export -> site.

Each stage is idempotent, so a run can be repeated, narrowed, or resumed. The
stages are also exposed individually through the CLI for cheap iteration.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import config, export, normalize, scoring, store
from .collectors import COLLECTORS
from .enrich import gemini


def collect(sources_cfg: Optional[Dict[str, Any]] = None, only: Optional[List[str]] = None, log=print) -> List[Dict[str, Any]]:
    sources_cfg = sources_cfg if sources_cfg is not None else config.load_sources()
    collected: List[Dict[str, Any]] = []
    for name, collector in COLLECTORS.items():
        if only and name not in only:
            continue
        cfg = sources_cfg.get(name) or {}
        if cfg.get("enabled") is False:
            log("%s: disabled" % name)
            continue
        log("%s: collecting" % name)
        try:
            items = collector(cfg, log=log)
        except Exception as exc:  # a failing source must not sink the run
            log("%s: FAILED (%s)" % (name, exc))
            continue
        collected.extend(items)
    return collected


def run(
    only: Optional[List[str]] = None,
    enrich: bool = True,
    enrich_limit: Optional[int] = None,
    build_site_dir: bool = True,
    log=print,
) -> Dict[str, Any]:
    started = store.utcnow()
    begin = time.time()
    sources_cfg = config.load_sources()
    conn = store.connect()
    store.init_db(conn)
    imported = store.import_cache_json(conn)
    if imported:
        log("cache: %d enrichment entries imported" % imported)

    log("stage 1/5 collect")
    raw_items = collect(sources_cfg, only=only, log=log)
    log("collected %d raw items" % len(raw_items))

    log("stage 2/5 normalise + dedupe")
    items = normalize.dedupe(raw_items)
    log("normalised to %d unique items" % len(items))

    log("stage 3/5 score")
    scoring.score_all(items)
    before = {item["id"] for item in store.all_items(conn)}
    inserted, updated = store.upsert_items(conn, items)
    log("store: %d inserted, %d updated" % (inserted, updated))

    stats: Dict[str, Any] = {
        "collected": len(raw_items),
        "unique": len(items),
        "inserted": inserted,
        "updated": updated,
        "enriched": 0,
        "cache_imported": imported,
    }

    if enrich:
        log("stage 4/5 enrich (Gemini free tier)")
        cfg = dict(sources_cfg.get("gemini") or {})
        if enrich_limit:
            cfg["max_requests_per_run"] = enrich_limit
        stored = store.all_items(conn)
        enrichment = gemini.enrich(conn, stored, cfg, log=log)
        stats["enriched"] = enrichment.get("enriched", 0)
        stats["enrich_cached"] = enrichment.get("cached", 0)
        stats["enrich_requests"] = enrichment.get("requests", 0)
        stats["enrich_errors"] = enrichment.get("errors", [])[:3]
        # Re-score: enrichment can flip self_hostable and category.
        refreshed = store.all_items(conn)
        scoring.score_all(refreshed)
        store.upsert_items(conn, refreshed)
    else:
        log("stage 4/5 enrich skipped")

    log("stage 5/5 export")
    index_path = export.write_index_json(conn)
    stats["index_json"] = str(index_path)
    stats["new_ids"] = len({item["id"] for item in store.all_items(conn)} - before)
    if build_site_dir:
        site = export.build_site(conn)
        stats["site_dir"] = str(site)
    stats["seconds"] = round(time.time() - begin, 1)

    store.record_run(conn, started, stats)
    conn.close()
    log("done in %ss: %s items, %s enriched" % (stats["seconds"], stats["unique"], stats["enriched"]))
    return stats
