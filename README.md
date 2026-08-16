# AI Visibility Intelligence API

Flask API that runs a three-agent pipeline to discover commercially relevant questions in a business's competitive space, score whether the brand would appear in AI/search answers for those questions, and recommend content to close the gaps.

1. **Query Discovery Agent** — GPT-4o generates 12–15 natural-language questions buyers ask AI assistants
2. **Visibility Scoring Agent** — DataForSEO supplies real search volume, keyword difficulty, search intent, and SERP / AI Overview visibility
3. **Content Recommendation Agent** — GPT-4o turns the highest-opportunity *not visible* queries into 3–5 concrete content briefs

The pipeline is **synchronous**. `POST /api/v1/profiles/{uuid}/run` blocks for roughly 10–30 seconds while the three agents run in sequence.

## Setup

### 1. Environment

```bash
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | GPT-4o for Agents 1 and 3 |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | API credentials from [DataForSEO API access](https://app.dataforseo.com/api-access) |
| `DATABASE_URL` | PostgreSQL URL (the docker-compose default matches `.env.example`) |
| `SECRET_KEY` | Flask secret |


### 2. Run with Docker Compose (recommended)

```bash
docker-compose up --build
```

This starts PostgreSQL, waits until it is healthy, runs `flask db upgrade`, and serves the app with gunicorn on [http://localhost:5000](http://localhost:5000).

Open the UI at [http://localhost:5000/](http://localhost:5000/) to register a business, run the pipeline, browse scored queries, and read content recommendations. JSON endpoints remain under `/api/v1`.

### 3. Run locally

PostgreSQL must already be running and match `DATABASE_URL`. Then:

```bash
flask --app app db upgrade
python run.py
```

`run.py` uses **Waitress** on Windows and **Gunicorn** on Linux/macOS. Gunicorn cannot start on Windows (`ModuleNotFoundError: No module named 'fcntl'` — `fcntl` is a Unix-only standard library).

For debug reloading on any OS:

```bash
flask --app app run --debug
```

UI: [http://localhost:5000/](http://localhost:5000/)

Health check: `GET http://localhost:5000/health`

## API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/profiles` | Register a business profile |
| `GET` | `/api/v1/profiles/{profile_uuid}` | Profile plus `total_queries` and `avg_opportunity_score` |
| `POST` | `/api/v1/profiles/{profile_uuid}/run` | Full pipeline (rate-limited: 5/hour/IP) |
| `GET` | `/api/v1/profiles/{profile_uuid}/queries` | `min_score`, `status=visible\|not_visible\|unknown`, `page`, `per_page` |
| `GET` | `/api/v1/profiles/{profile_uuid}/recommendations` | Agent 3 output |
| `POST` | `/api/v1/queries/{query_uuid}/recheck` | Re-run Agent 2 for one query |

Authentication is not Implemented:

```json
{ "error": { "code": "not_found", "message": "Profile not found" } }
```

### Example

```bash
curl -X POST http://localhost:5000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Surfer SEO\",
    \"domain\": \"surferseo.com\",
    \"industry\": \"SEO Software\",
    \"description\": \"AI-powered SEO content optimization tool\",
    \"competitors\": [\"clearscope.io\", \"marketmuse.com\", \"frase.io\"]
  }"
```

```bash
curl -X POST http://localhost:5000/api/v1/profiles/{profile_uuid}/run
```

## Architecture

```
Browser UI  (/)  ──►  Jinja views (same models)
JSON client (/api/v1) ──►  Flask API blueprints
                              → Pipeline orchestrator
                                  → QueryDiscoveryAgent        (OpenAI gpt-4o, JSON mode)
                                  → VisibilityScoringAgent     (DataForSEO only — no LLM)
                                  → ContentRecommendationAgent (OpenAI gpt-4o, JSON mode)
                              → PostgreSQL (SQLAlchemy + Flask-Migrate)
```

The UI is server-rendered Jinja + plain CSS. **Run pipeline** and **Recheck** call the existing JSON endpoints (`POST /api/v1/profiles/{uuid}/run` and `POST /api/v1/queries/{uuid}/recheck`), so they use the live OpenAI and DataForSEO pipeline — typically 10–30 seconds, with a loading overlay.

`create_app()` is the Flask application factory. Blueprints, SQLAlchemy, Flask-Migrate, and Flask-Limiter are wired there. Each pipeline run gets a UUID that is written on every log line as `run_uuid` so a 30-second run is easy to trace.

### Agent design

Agents are independently constructible (inject an OpenAI client or a DataForSEO client). The orchestrator is the only place that talks to the database.

**Agent 1** is a GEO researcher persona. The system prompt pins the output schema, question mix (best-of, vs, how-to, pricing), and a `seed_keyword` field. Conversational questions such as "What is the best SEO content tool?" often have **no Google Ads volume**; the seed keyword (`best seo content tool`) is what we send to DataForSEO.

**Agent 2** never calls the LLM. It:

1. Batches seed keywords to `keywords_data/google_ads/search_volume/live`
2. Batches `dataforseo_labs/google/bulk_keyword_difficulty/live`
3. Batches `dataforseo_labs/google/search_intent/live`
4. Checks visibility with `serp/google/organic/live/advanced` (4 parallel workers)

A domain counts as **visible** if it appears in organic results **or** in Google AI Overview citations / overview text. `visibility_position` is the organic rank when ranked, otherwise the AI Overview citation index. If a single SERP call fails, that query is stored as `visibility_status=unknown` and the rest of the batch continues.

**Agent 3** only sees gap queries (`not_visible`), ranked by opportunity. Invalid recommendation items are dropped; a total Agent 3 failure does not fail the run — queries are already saved.

LLM JSON handling: `response_format=json_object`, Pydantic validation, one repair retry that includes the validation error, then a typed `AgentOutputError`. The pipeline does not crash on malformed model output.

## Opportunity score

```
volume_norm = log10(1 + volume) / log10(1 + 10000)   # cap at 10k monthly searches
ease        = 1 - (difficulty / 100)
gap         = 1.0 if not visible
            = 0.0 if visible at position 1
            = min(1.0, (position - 1) / 10) otherwise
            = 0.7 if visibility is unknown
intent_w    = transactional 1.00 | commercial 0.85 | informational 0.45 | navigational 0.15

score = clip(
    0.35 * volume_norm
  + 0.25 * ease
  + 0.25 * gap
  + 0.15 * intent_w
, 0, 1)
```

Demand and the visibility gap carry the most weight because that is the product question: *would it be valuable for this domain to appear in the answer?* Easy keywords and commercial/comparison intent still move a query up the list. Unknown visibility is treated as a likely gap (0.7) so a flaky SERP call does not bury a good query.

Implemented in `app/utils/scoring.py`.

## Schema extras

Required entities are `BusinessProfile`, `PipelineRun`, `DiscoveredQuery`, and `ContentRecommendation`, with UUID primary keys.

Added fields, and why:

| Field | Why |
|---|---|
| `DiscoveredQuery.seed_keyword` | Google Ads rejects long questions; this is the lookup key |
| `DiscoveredQuery.search_intent` / `commercial_intent_score` | Feeds the intent term of the formula and is useful in the UI later |
| `DiscoveredQuery.visibility_status` | Powers `?status=visible\|not_visible\|unknown` without nullable-boolean ambiguity |
| `ContentRecommendation.run_uuid` | Groups recommendations by the run that produced them |
| `PipelineRun.correlation_id` | Same value as the run UUID; used in structured logs |

## Tests

```bash
python -m pytest
```

LLM and DataForSEO are mocked. Coverage is aimed at agent JSON fallback, the scoring formula, orchestrator partial failure, and request validation — not live provider calls.

## Tradeoffs

- **Synchronous pipeline.** The spec allows it and it keeps the assessment readable. Celery + a poll endpoint would be the production next step; gunicorn `--timeout 120` covers the 10–30s run.
- **SERP + AI Overview as the visibility signal**, not 15 live ChatGPT scrapes via DataForSEO LLM Responses. Live LLM Responses can take up to 120s *each* and would blow both latency and trial credits. Organic rank plus AI Overview citations are still *real* third-party data and map cleanly onto `visibility_position`.
- **Seed keywords.** Honest about Google Ads coverage for conversational queries rather than fabricating volume.
- **No auth.** Out of scope.
- **In-memory rate-limit storage.** Fine for a single gunicorn process; Redis would be needed to share limits across workers.

## Project layout

```
app/
  __init__.py          create_app()
  config.py
  extensions.py        db, migrate, limiter
  errors.py            JSON for /api and /health; HTML for the UI
  agents/              discovery, scoring, recommendation
  api/                 Flask JSON blueprints
  web/                 Jinja UI (dashboard, profile, queries, recs)
  templates/           HTML
  static/              plain CSS + vanilla JS
  models/
  schemas/             Pydantic (requests + LLM output)
  services/            pipeline orchestrator + DataForSEO client
  utils/               opportunity score, JSON parse, domain helpers
migrations/
tests/
```
