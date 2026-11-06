# Sources

All sources are free and require no paid plan. Keyless access is the default; a
key only raises limits.

| Source | Module | Key | Limits | What it contributes |
| --- | --- | --- | --- | --- |
| GitHub repository search | `collectors/github.py` | none (`GITHUB_TOKEN` optional) | 10 search requests/min unauthenticated, 30 with a token | identity, stars, licence, language, topics, last push |
| Hacker News (Algolia) | `collectors/hackernews.py` | none | generous, please pace | community signal, discussion links, launch detection |
| Curated awesome-lists | `collectors/awesome.py` | none | raw.githubusercontent.com | human-written descriptions, "actually usable" signal |
| Google Gemini | `enrich/gemini.py` | `GEMINI_API_KEY` (free tier) | requests/minute and per-day caps; see your AI Studio quota page | summaries, category, tags, maturity, difficulty, self-hostability |

## GitHub queries

Configured in `config/sources.json`. Each query is a GitHub search expression; the
collector appends `stars:>=N` when the query does not already set a star filter.
Queries are topic-based (`topic:llm`, `topic:ai-agents`, `topic:rag`,
`topic:llm-serving`, `topic:vector-database`, `topic:local-llm`, …) so results stay
on-topic rather than picking up every repository that merely mentions "AI".

Add a query by appending to the list — no code change. Keep `max_requests` in step
with the rate limit and `request_delay_seconds` high enough not to be throttled
(unauthenticated: 7s, with a token: 2s).

## Hacker News queries

`search_by_date` with `points>min_points` and a `days` window. Stories whose URL is
a repository already in the index are merged into that repository (source
`hackernews` + discussion link), so news never duplicates a project card. Stories
about projects that are *not* in the index appear as their own `news` entries and
are a good prompt to widen the GitHub queries.

## Curated lists

Listed as `owner/repo` in `config/sources.json`; the collector tries the `main` then
the `master` branch and parses markdown bullet links. Entries pointing at GitHub
repositories reuse the `gh:owner/repo` id, so they merge with GitHub data and simply
add the `curated` source (which also contributes to the score).

The default set is deliberately small. Good lists to add when you want more
breadth:

```jsonc
"lists": [
  "e2b-dev/awesome-ai-agents",
  "steven2358/awesome-generative-ai",
  "kyrolabs/awesome-langchain",
  "awesome-selfhosted/awesome-selfhosted",
  "hindupuravinash/the-awesome-AI-generated-content",
  "mahseema/awesome-ai-tools",
  "EthicalML/awesome-production-machine-learning"
]
```

## Free-tier etiquette

- One scheduled refresh per day is plenty; the upstream projects change slowly.
- The pipeline is polite by construction: a delay between requests, retries with
  exponential backoff, and a request cap per run.
- Never send a request per item to Gemini: batching is what keeps the free tier
  viable (12 items per request by default).
- Cache before you call: `data/enrichment-cache.json` is the record of what has
  already been paid for with quota.

## Known limits

- GitHub search returns at most 1000 results per query (10 pages of 100); the index
  therefore samples the top-starred results per query rather than everything.
- Star counts are popularity, not quality. Curation and activity are weighted in
  the score for exactly that reason.
- Licence strings come from the source. `NOASSERTION` is normalised to `Unknown`
  and shown as such rather than guessed.
- Hacker News points decay; the `days` window keeps the news facet fresh.
