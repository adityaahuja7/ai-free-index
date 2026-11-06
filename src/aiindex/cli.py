"""Command line interface: python -m aiindex <command>."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, config, export, normalize, scoring, server, store
from .collectors import COLLECTORS
from .enrich import gemini
from . import pipeline


def _print(message: str = "") -> None:
    print(message, flush=True)


def cmd_collect(args) -> int:
    sources = config.load_sources()
    only = args.only.split(",") if args.only else None
    items = pipeline.collect(sources, only=only, log=_print)
    items = normalize.dedupe(items)
    scoring.score_all(items)
    conn = store.connect()
    store.init_db(conn)
    inserted, updated = store.upsert_items(conn, items)
    conn.close()
    _print("stored: %d inserted, %d updated" % (inserted, updated))
    return 0


def cmd_enrich(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    store.import_cache_json(conn)
    cfg = dict(config.load_sources().get("gemini") or {})
    if args.limit:
        cfg["max_requests_per_run"] = args.limit
    items = store.all_items(conn)
    stats = gemini.enrich(conn, items, cfg, log=_print)
    _print(json.dumps(stats, indent=2))
    conn.close()
    return 0


def cmd_export(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    path = export.write_index_json(conn)
    payload = export.build_payload(conn)
    conn.close()
    _print("wrote %s (%d items)" % (path, payload["stats"]["total"]))
    return 0


def cmd_site(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    target = export.build_site(conn)
    conn.close()
    _print("site built at %s" % target)
    return 0


def cmd_build(args) -> int:
    config.load_dotenv()
    stats = pipeline.run(
        only=args.only.split(",") if args.only else None,
        enrich=not args.no_enrich,
        enrich_limit=args.enrich_limit,
        build_site_dir=not args.no_site,
        log=_print,
    )
    _print(json.dumps({k: v for k, v in stats.items() if k != "enrich_errors"}, indent=2))
    if stats.get("enrich_errors"):
        _print("enrich errors: %s" % stats["enrich_errors"])
    return 0


def cmd_serve(args) -> int:
    config.load_dotenv()
    if args.build:
        pipeline.run(enrich=not args.no_enrich, log=_print)
    site = config.site_dir()
    if not (site / "data" / "index.json").exists():
        conn = store.connect()
        store.init_db(conn)
        site = export.build_site(conn)
        conn.close()
    server.serve(site, port=args.port, host=args.host, open_browser=args.open)
    return 0


def cmd_stats(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    payload = export.build_payload(conn)
    conn.close()
    _print(json.dumps({"stats": payload["stats"], "generated_at": payload["generated_at"]}, indent=2))
    return 0


def cmd_doctor(args) -> int:
    """Explain the environment without ever printing a secret."""
    conn = store.connect()
    store.init_db(conn)
    items = store.all_items(conn)
    cache = store.cache_get(conn, "0" * 40, "probe", "probe")
    conn.close()
    keys = config.gemini_keys()
    report = {
        "version": __version__,
        "repo_root": str(config.repo_root()),
        "database": str(config.db_path()),
        "database_exists": config.db_path().exists(),
        "items_in_db": len(items),
        "index_json": str(config.index_json_path()),
        "index_json_exists": config.index_json_path().exists(),
        "site_dir": str(config.site_dir()),
        "gemini_keys_found": len(keys),
        "gemini_model": config.gemini_model(),
        "github_token": bool(config.github_token()),
        "collectors": sorted(COLLECTORS),
        "enrichment_enabled": gemini.available(),
        "cache_lookup_ok": cache is None,
    }
    _print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiindex",
        description="Collect, enrich and publish an index of free and open-source AI software.",
    )
    parser.add_argument("--version", action="version", version="ai-free-index %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    p_collect = sub.add_parser("collect", help="collect from all enabled sources and store")
    p_collect.add_argument("--only", help="comma separated sources: github,hackernews,awesome")
    p_collect.set_defaults(func=cmd_collect)

    p_enrich = sub.add_parser("enrich", help="enrich stored items with Gemini")
    p_enrich.add_argument("--limit", type=int, default=None, help="max requests this run")
    p_enrich.set_defaults(func=cmd_enrich)

    p_export = sub.add_parser("export", help="write data/index.json from the database")
    p_export.set_defaults(func=cmd_export)

    p_site = sub.add_parser("site", help="assemble the deployable static site in _site/")
    p_site.set_defaults(func=cmd_site)

    p_build = sub.add_parser("build", help="full pipeline: collect, enrich, export, site")
    p_build.add_argument("--only", help="comma separated sources")
    p_build.add_argument("--no-enrich", action="store_true", help="skip Gemini enrichment")
    p_build.add_argument("--enrich-limit", type=int, default=None, help="max Gemini requests")
    p_build.add_argument("--no-site", action="store_true", help="skip _site assembly")
    p_build.set_defaults(func=cmd_build)

    p_serve = sub.add_parser("serve", help="serve the dashboard locally")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--open", action="store_true", help="open a browser")
    p_serve.add_argument("--build", action="store_true", help="run the pipeline first")
    p_serve.add_argument("--no-enrich", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_stats = sub.add_parser("stats", help="print index statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_doctor = sub.add_parser("doctor", help="print environment and configuration state")
    p_doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    config.load_dotenv()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
