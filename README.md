<!-- testing CI -->
# BehaviorCI

**The git diff for AI behavior.**

Behavioral regression testing for LLM-powered products. Tracks not just whether
a score dropped, but whether your model's tone, reasoning style, or accuracy
changed across model updates, prompt edits, or fine-tuning runs.

This repo implements the core engine end-to-end and is fully tested:
test case management (YAML-defined), the AI evaluator agent (LLM-as-judge +
embeddings), the regression diff engine, a REST API, a web dashboard, a CLI,
and a GitHub Actions integration.

**Total cost to run this: $0.** Every default uses free/local components —
no credit card, no API key, no paid tier required anywhere.

---

## How it's free

| Piece | Paid option in the original spec | Free option used here (default) |
|---|---|---|
| LLM judge | Claude / GPT-4o via API | **Ollama** running a local open model (e.g. Llama 3.1 8B) on your own machine |
| Embeddings | OpenAI `text-embedding-3-small` | **sentence-transformers** (`all-MiniLM-L6-v2`), runs locally on CPU |
| Database | Managed Postgres | **SQLite** file (zero setup) or free-tier Postgres (Supabase/Neon, see below) |
| Task queue | Celery + Redis (hosted) | **asyncio** with a bounded semaphore — no extra service to run or pay for |
| Hosting | Render/Fly paid tier | Run locally, or deploy on a free tier (see "Free deployment" below) |
| CI | — | **GitHub Actions** is free for public repos and has free minutes for private ones |

You can swap any row back to the paid option later just by changing values
in `.env` — nothing in the code is hard-wired to the free path.

---

## 1. Local setup (fastest way to see it working)

### Prerequisites (all free)
- Python 3.11+
- [Ollama](https://ollama.com/download) — free local LLM runner (Mac/Windows/Linux)

### Steps

```bash
# 1. Clone / unzip the project, then:
cd behaviorci
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Ollama and pull a small free model (one-time, ~5GB download)
#    Get Ollama from https://ollama.com/download, then:
ollama pull llama3.1:8b
# If your machine is low on RAM, use a smaller model instead and update
# OLLAMA_MODEL in .env, e.g.:
#   ollama pull llama3.2:3b

# 4. Configure environment
cp .env.example .env
# Defaults already point at SQLite + local Ollama + local embeddings.
# No changes required to get started.

# 5. Initialize the database and a default org/project
python cli.py init
# -> prints: Initialized. project_id=<uuid>      (save this id)

# 6. Load the example test suite
python cli.py sync test_cases/customer_support_suite.yaml
# -> prints: Synced suite 'Customer Support Bot' (id=<uuid>) with 6 test cases.
#    (save this suite id too)

# 7. Start the API + dashboard
uvicorn app.main:app --reload
```

Open **http://localhost:8000** — you'll see the dashboard.
Open **http://localhost:8000/docs** for the interactive API docs (Swagger UI).

### Running a suite against your model

BehaviorCI doesn't call your model for you — it's framework-agnostic by
design (works with OpenAI, Anthropic, Gemini, or anything else). You give it
an HTTP endpoint that accepts `{"prompt": "..."}` and returns `{"output": "..."}`,
and BehaviorCI handles the rest: calling it for every test case, judging the
results, and diffing against the last run.

A minimal wrapper around your own model, for testing purposes, looks like this:

```python
# my_model_endpoint.py - a tiny FastAPI app that wraps whatever you're testing
from fastapi import FastAPI
import anthropic  # or openai, or your own client

app = FastAPI()
client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY from your own env

@app.post("/generate")
async def generate(payload: dict):
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": payload["prompt"]}],
    )
    return {"output": response.content[0].text}
```

```bash
# run it on a separate port
uvicorn my_model_endpoint:app --port 9000

# then trigger a BehaviorCI run against it
python cli.py run <suite_id> http://localhost:9000/generate
```

Run it again after changing your prompt/model and BehaviorCI will show you
exactly what changed — that's the regression diff.

---

## 2. Docker Compose setup (closer to "production-like", still free)

```bash
docker compose up -d
docker exec -it behaviorci-ollama-1 ollama pull llama3.1:8b
```

This spins up Postgres, Ollama, and the API together. Visit `http://localhost:8000`.

---

## 3. Project structure

```
behaviorci/
├── app/
│   ├── main.py              # FastAPI app entrypoint
│   ├── config.py            # settings, all free-by-default
│   ├── database.py          # SQLAlchemy engine/session
│   ├── models.py            # 6 core tables (orgs, projects, suites, cases, runs, results)
│   ├── schemas.py           # Pydantic request/response models
│   ├── routers/
│   │   ├── projects.py      # /api/organizations, /api/projects
│   │   ├── suites.py        # /api/suites, /api/test-cases, YAML sync
│   │   ├── runs.py          # /api/suites/{id}/run, /api/runs/{id}
│   │   └── dashboard.py     # HTML pages (/  /suite/{id}  /run/{id})
│   ├── services/
│   │   ├── evaluator.py     # llm_judge() + embed() -- the AI evaluator agent
│   │   ├── test_runner.py   # fan-out parallel execution of test cases
│   │   ├── diff_engine.py   # regression detection: metric/pass-fail/drift/patterns
│   │   └── yaml_loader.py   # loads YAML test suites into the DB
│   └── templates/           # dashboard HTML (dark, git-diff styled)
├── test_cases/
│   └── customer_support_suite.yaml   # example suite, ready to run
├── tests/
│   └── test_core_logic.py   # unit tests for the diff engine (no external services needed)
├── cli.py                   # `python cli.py init|sync|run|report`
├── docker-compose.yml
├── Dockerfile
├── .github/workflows/behaviorci.yml   # CI integration template
├── requirements.txt
└── .env.example
```

---

## 4. Writing test cases (YAML)

```yaml
suite_name: "Customer Support Bot"
description: "Regression suite for tone, accuracy, refund policy."

test_cases:
  - name: "refund_policy_basic"
    input_prompt: "How long do I have to request a refund?"
    expected_behavior: "States the 30-day window, friendly, concise, no invented conditions."
    criteria:
      numeric:
        correctness_min: 0.85
      semantic:
        max_words: 80
      behavioral:
        tone: "friendly_professional"
    tags: ["refunds", "policy"]
```

Sync it with: `python cli.py sync test_cases/your_suite.yaml`

The four criteria types map directly to the documented design:
- **numeric** → checked against the judge's numeric scores (e.g. `correctness_min`)
- **format** → structural rules, reflected in the judge's `format` score
- **semantic** → computed via embeddings (`semantic_similarity`), not by asking the LLM — faster and more consistent
- **behavioral** → tone/style/reasoning checks, reflected in the judge's `behavioral` score

---

## 5. The regression diff engine

After every run, BehaviorCI automatically compares it to the previous run for
the same suite and detects four kinds of regression:

1. **Metric regression** — any dimension score dropped more than the
   threshold (default `0.10`, set via `REGRESSION_SCORE_THRESHOLD`)
2. **Pass/fail flips** — tests that passed last time and fail now
3. **Behavioral drift** — output embeddings moved apart by more than
   `DRIFT_DISTANCE_THRESHOLD` even when scores looked fine (tone/personality
   changed without "breaking" anything measurable)
4. **Systemic patterns** — failures clustering around a shared tag (≥50% of
   cases with that tag degraded), flagging a likely root cause rather than
   isolated noise

View it in the dashboard at `/run/{run_id}`, or via `python cli.py run` which
prints the report and **exits with a non-zero status code if regressions are
found** — this is what makes a CI pipeline fail the build automatically.

---

## 6. CI/CD integration (GitHub Actions)

`.github/workflows/behaviorci.yml` is included and:
- Installs Ollama and pulls a model directly on the GitHub-hosted runner (free minutes)
- Syncs your YAML test suite
- Runs it against a staging endpoint of your product
- Posts the regression report as a PR comment
- Fails the build if regressions are detected

Set these as repo Variables (Settings → Secrets and variables → Actions → Variables):
- `BEHAVIORCI_SUITE_ID` — the suite id from `cli.py sync`
- `STAGING_MODEL_ENDPOINT` — your staging environment's `/generate`-style endpoint

---

## 7. Free deployment (optional — if you want this reachable outside your laptop)

You do not have to deploy anything to use this — running locally is enough
for personal/team use behind a VPN, or for CI. If you want a hosted URL:

| Component | Free option |
|---|---|
| Postgres | [Supabase](https://supabase.com) or [Neon](https://neon.tech) free tier (500MB–10GB, no card required for Neon) |
| API hosting | [Render](https://render.com) free Web Service tier, or [Fly.io](https://fly.io) free allowance |
| LLM judge | Keep using local Ollama on your own machine/server you control — hosted "free" LLM APIs usually require a card on file. If you must host the judge itself, Anthropic and OpenAI both offer small free trial credits for new accounts — check current terms before relying on this. |
| Dashboard | Served by the same FastAPI app — no separate hosting needed |

Update `DATABASE_URL` in your deployment's environment variables to point at
the free Postgres instance, and `OLLAMA_HOST` to wherever you're running
Ollama (it needs to be reachable from your API host — a small always-on
machine, or your own server, works; serverless free tiers usually can't run
Ollama itself due to its memory/GPU needs).

---

## 8. Going to production later (optional, not required for free use)

These are upgrades, not requirements — everything above is a complete,
working product as-is:

- Swap SQLite for Postgres and add Alembic migrations
- Swap the asyncio runner for Celery + Redis if you need true multi-worker
  horizontal scaling beyond what one process can handle
- Switch `JUDGE_MODE=anthropic` or `openai` in `.env` if you want a stronger
  judge model and are fine paying API costs per evaluation
- Add auth (e.g. JWT or an auth provider) to the API before exposing it publicly
- Add the team/billing/Slack-alert layer described in the original product
  spec — the roadmap's own advice is correct: build this core first, validate
  it works for your real use case, then layer on the SaaS features

---

## 9. Troubleshooting

- **`ollama.ResponseError` / connection refused** — make sure `ollama serve`
  is running (the desktop app does this automatically; on Linux you may need
  `ollama serve &` in a terminal) and that `OLLAMA_HOST` in `.env` matches.
- **Judge returns invalid JSON occasionally** — local models are less
  reliable at strict JSON than Claude/GPT-4o. `evaluator.py` already retries
  parsing leniently (strips code fences, extracts the first JSON object). If
  you see frequent failures, try a larger model (`llama3.1:8b` instead of a
  3B model) or switch `JUDGE_MODE=anthropic` for evaluation only.
- **First run is slow** — `sentence-transformers` downloads the embedding
  model (~90MB) once on first use, then it's cached locally.
- **SQLite "database is locked"** — happens under heavy concurrent writes;
  fine for development, switch to Postgres (still free via Supabase/Neon)
  if you hit this in regular use.

---

BehaviorCI — the git diff for AI behavior.
