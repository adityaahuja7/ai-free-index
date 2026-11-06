# AI Free Software Index

A maintained index of **free and open-source AI software** — models, agents,
serving stacks, RAG tooling, speech, vision, and developer tools — collected from
free sources, enriched with the Google Gemini free tier, and published as a rich
static dashboard.

- **Collect** from GitHub search, Hacker News (Algolia) and curated awesome-lists.
- **Enrich** with Gemini: one-line summaries, categories, tags, self-hostability,
  maturity, target user and setup difficulty.
- **Rank** with a transparent 0–100 score (popularity, activity, openness,
  curation, discussion) that the dashboard explains per item.
- **Publish** a dependency-free dashboard to GitHub Pages, any static host, or a
  container. No paid APIs, no paid infrastructure, no build step for the front-end.

## Quickstart

```bash
git clone https://github.com/<you>/ai-free-index.git
cd ai-free-index

# optional but recommended: Gemini free-tier key for AI enrichment
cp .env.example .env && $EDITOR .env

# run the whole pipeline and serve the dashboard locally
make serve          # == PYTHONPATH=src python -m aiindex serve --build --open
```

Open <http://127.0.0.1:8000/>. Without any key the pipeline still runs; the
dashboard simply shows fewer editorial fields.

## Commands

| Command | What it does |
| --- | --- |
| `aiindex build` | Full pipeline: collect → dedupe → score → store → enrich → export → `_site/` |
| `aiindex collect [--only github,hackernews,awesome]` | Collect and store only |
| `aiindex enrich [--limit N]` | Enrich stored items with Gemini (cache-aware) |
| `aiindex export` | Rebuild `data/index.json` from the database |
| `aiindex site` | Assemble the deployable static site in `_site/` |
| `aiindex serve [--build] [--port 8000] [--host 0.0.0.0]` | Serve the dashboard locally |
| `aiindex stats` / `aiindex doctor` | Print index statistics / environment state (never prints secrets) |

Run it as `PYTHONPATH=src python -m aiindex <command>` or install it with
`pip install -e .` to get the `aiindex` entry point.

## Layout

```
config/sources.json     sources, queries, budgets and enrichment settings
src/aiindex/
  collectors/           github.py, hackernews.py, awesome.py
  enrich/gemini.py      Gemini free-tier client, batching, cache, key rotation
  normalize.py          licences, categories, tags, free-ness flags, de-duplication
  scoring.py            transparent 0-100 index score
  store.py              SQLite schema, upserts, enrichment cache, run history
  export.py             data/index.json + _site assembly
  server.py             standard-library dev server
  pipeline.py, cli.py   orchestration and command line
web/                    the dashboard (HTML + CSS + vanilla JS, no build step)
data/                   index.json (committed) + SQLite + enrichment cache export
docs/                   architecture, sources, deployment
tests/                  offline unit tests
.github/workflows/      scheduled refresh + GitHub Pages deploy
```

## Data model

`data/index.json` is the published contract. Each item carries identity and
upstream metrics (`name`, `url`, `stars`, `language`, `license`, `pushed_at`),
editorial fields (`summary`, `category`, `tags`, `maturity`, `target_user`,
`difficulty`, `self_hostable`, `free_tier_notes`), provenance (`sources`,
`first_seen`, `last_seen`, `enrichment_model`) and the score with its
`score_parts` breakdown. Items keep their upstream link so attribution is intact.

## Tests

```bash
make test     # PYTHONPATH=src python -m unittest discover -s tests -v
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for GitHub Pages, static hosts,
Docker, and scheduled refreshes. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for how the stages fit together and [docs/SOURCES.md](docs/SOURCES.md) for the
source list and its limits.

## Licence

MIT — see [LICENSE](LICENSE). The indexed projects keep their own licences; the
dashboard always links to the upstream repository.
