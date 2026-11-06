# Deployment

Everything here runs on free tiers. The dashboard is static, so hosting is a
static-file problem; the pipeline needs only Python 3.9+ and outbound HTTPS.

## 0. Prerequisites

| Need | Why | Cost |
| --- | --- | --- |
| Python 3.9+ | runs the pipeline | free |
| Gemini API key from [AI Studio](https://aistudio.google.com/apikey) | AI enrichment (optional) | free tier |
| GitHub token | raises search limits; Actions provides one automatically | free |

Never commit `.env`. Only `.env.example` belongs in the repository.

## 1. Local

```bash
cp .env.example .env         # add GEMINI_API_KEY if you have one
make build                   # collect + enrich + export + _site/
make serve                   # http://127.0.0.1:8000
make test                    # offline unit tests
make doctor                  # environment check, prints no secrets
```

Refresh on a schedule with cron:

```bash
./scripts/install-cron.sh    # daily 06:15 local, logs to data/refresh.log
```

## 2. GitHub Actions (recommended)

1. Push the repository to GitHub.
2. **Settings → Secrets and variables → Actions** → add `GEMINI_API_KEY`
   (and optionally `GEMINI_API_KEYS` with several free keys, comma separated).
3. **Settings → Actions → General → Workflow permissions** → allow *Read and write*
   so the refresh workflow can commit `data/`.
4. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. Run the *Refresh index* workflow once (Actions → Refresh index → Run workflow),
   then the *Deploy dashboard* workflow. The dashboard appears at
   `https://<user>.github.io/<repo>/`.

What the workflows do:

- `refresh.yml` — daily at 01:15 UTC and on demand: runs the pipeline, prints
  statistics, commits `data/index.json` and `data/enrichment-cache.json`.
  Only data is committed, so history stays readable.
- `pages.yml` — on pushes that touch `web/`, `data/index.json` or `src/`: assembles
  `_site/` and deploys it to Pages.
- `tests.yml` — runs the offline unit tests plus `aiindex doctor` on every push.

The enrichment cache is committed on purpose: it means each CI run only pays for
items that are new or whose metadata changed, which is what keeps the free Gemini
tier sufficient.

## 3. Any static host (Netlify, Cloudflare Pages, S3, nginx)

```bash
PYTHONPATH=src python -m aiindex site   # produces _site/
```

Publish `_site/` as-is. It contains `index.html`, `styles.css`, `app.js`,
`favicon.svg` and `data/index.json`. No server-side runtime, no build step.

- **Netlify / Cloudflare Pages**: build command `PYTHONPATH=src python -m aiindex site`,
  publish directory `_site`.
- **S3 + CloudFront**: `aws s3 sync _site/ s3://<bucket>/ --delete`, then invalidate.
- **nginx**: `root /var/www/ai-free-index/_site;` (the site is fully static).

To refresh a static host, run the pipeline in CI (e.g. the same Actions workflow,
or a cron on a small box) and re-upload `_site/`.

## 4. Docker

```bash
docker build -t ai-free-index .
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=... ai-free-index
```

The image builds the index on start (cheap without a key) and serves it on
`0.0.0.0:8000`. With compose:

```bash
export GEMINI_API_KEY=...
docker compose up -d --build
```

`./data` is mounted, so the database and the enrichment cache survive restarts.
Refresh inside a running container with:

```bash
docker compose exec index python -m aiindex build
```

## 5. Configuration

`config/sources.json` controls everything without code changes:

```jsonc
{
  "github":     { "min_stars": 150, "max_requests": 12, "request_delay_seconds": 7, "queries": [...] },
  "hackernews": { "min_points": 25, "days": 45, "queries": [...] },
  "awesome":    { "lists": ["owner/repo", ...] },
  "gemini":     { "model": "gemini-2.5-flash", "batch_size": 12, "max_requests_per_run": 40 }
}
```

Budgets that matter for staying free:

- `github.max_requests` — unauthenticated search allows 10 requests/minute; with a
  token, 30. The collector paces itself with `request_delay_seconds`.
- `gemini.max_requests_per_run` — caps daily free-tier usage. Each request covers
  `batch_size` items.
- `hackernews.days` / `min_points` — keeps the news stream small and relevant.

## 6. Operating notes

- **Quota exhausted**: the run continues without enrichment and logs the reason;
  `data/enrichment-cache.json` means the next run does not repeat work.
- **Model changes**: changing `gemini.model` or `prompt_version` re-enriches
  everything once (that is intended, and it is also how you recover from a bad
  prompt). Raise `max_requests_per_run` for that one run if you want it done fast.
- **Backups**: `data/index.json` plus `data/enrichment-cache.json` are enough to
  rebuild the dashboard; the SQLite file is disposable.
- **Rollback**: the index is data, not code — `git revert` the data commit.
- **Attribution**: every item links to its upstream project; licences are recorded
  as reported by the source and shown in the dashboard, but always check the
  upstream repository before reuse.
