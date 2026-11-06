# Architecture

```
                 free sources                       enrichment (free tier)
   GitHub search ─┐                                   Google Gemini
   Hacker News  ──┼─► collectors ─► normalize ─► score ─► store (SQLite) ─► enrich
   awesome-lists ─┘                 dedupe       0-100       ▲   │
                                                            │   ▼
                              data/enrichment-cache.json ◄──┘  export ─► data/index.json
                                                                          │
                                                                    web/ + data ─► _site/ ─► Pages / container
```

## Stages

1. **Collect** (`src/aiindex/collectors/`) — one module per source, each taking its
   own config block from `config/sources.json`. Collectors only produce dicts with
   `id`, `source`, `kind`, `name`, `url` plus whatever the source offers. A failing
   source is logged and skipped; it never fails the run.
2. **Normalise** (`normalize.py`) — licence normalisation against an OSI-style
   allow-list, topic cleanup, deterministic category/tag guesses, self-hostability
   heuristics, and de-duplication. Duplicate rules:
   - identical `id` (e.g. `gh:owner/repo` from both GitHub and a curated list) is merged;
   - a Hacker News story pointing at a repository already indexed is merged into that
     repository (adding a `hackernews` source and a discussion link) instead of
     creating a second card.
3. **Score** (`scoring.py`) — a 0–100 index score with published weights:
   popularity 0.42 (log-scaled stars), activity 0.24 (days since last push, 2-year
   horizon), openness 0.14 (free licence), curation 0.12 (present in a curated
   list), discussion 0.08 (Hacker News points). The parts are stored per item and
   shown in the dashboard, so ranking is never a black box.
4. **Store** (`store.py`) — SQLite is the source of truth. `data/index.json` is the
   published artefact; `data/enrichment-cache.json` carries the paid-for-once
   Gemini answers across CI runs. `first_seen`/`last_seen` make growth visible.
5. **Enrich** (`enrich/gemini.py`) — batched calls to the Generative Language API
   with a JSON response schema. Order of protection for the free quota: cache
   lookup → request cap per run → pacing between requests → multi-key rotation →
   `RetryInfo`-aware backoff → graceful degradation. Nothing here is required for
   the pipeline to succeed.
6. **Export / publish** (`export.py`, `server.py`) — `data/index.json` plus the
   static `web/` assets are assembled into `_site/`, which is what GitHub Pages,
   any static host, or the container serves.

## Why the standard library only

The whole pipeline runs on a free runner, in a slim container, and on a laptop with
no install step. `urllib` handles HTTP, `sqlite3` handles storage, `http.server`
serves the dashboard. Fewer moving parts also means fewer things to break at 01:15.

## Extending

- **New source**: add `collectors/<name>.py` exposing `collect(cfg, log=print)`,
  register it in `collectors/__init__.py`, add a block to `config/sources.json`.
- **New enrichment field**: extend `RESPONSE_SCHEMA` in `enrich/gemini.py`, bump
  `prompt_version`, add the column in `store.SCHEMA` and `store.FIELDS`, then surface
  it in `export.ITEM_FIELDS` and the dashboard.
- **New ranking signal**: add it to `scoring.py` with an explicit weight and expose
  the part in `score_parts` so the dashboard can explain it.
