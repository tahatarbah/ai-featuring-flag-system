# Warden Technical Tutorial

A full walkthrough of the AI Feature Flag System with Gradual Rollout and Quality Monitoring — architecture, data model, evaluation rules, APIs, SDK, admin UI, quality gates, and how to operate it locally.

---

## 1. What this system is

**Warden** is a control plane for shipping AI changes the way product teams ship feature flags:

- Multivariate payloads (model, prompt, temperature) instead of only booleans
- Sticky percentage rollouts so the same user stays on the same variant
- Targeting rules for allow-lists
- Quality SLOs that compare treatment vs control
- Automatic pause / rollback when quality slips
- Instant kill switch that forces everyone to control

It is **not** a multi-tenant SaaS, not a prompt IDE, and not a full observability stack. One demo product (support assistant) proves the loop end to end.

---

## 2. Architecture

```text
┌──────────────────┐     ┌────────────────────────────┐     ┌────────────┐
│  Admin UI (Vite) │────▶│  FastAPI control plane      │────▶│  Postgres  │
│  :5173           │     │  flags · SDK · demo · gates │     │  aiflags   │
└──────────────────┘     └─────────────┬──────────────┘     └────────────┘
                                       │
                         ┌─────────────┴──────────────┐
                         │  Python SDK (local eval)   │
                         │  poll config · batch events│
                         └─────────────┬──────────────┘
                                       │
                         ┌─────────────┴──────────────┐
                         │  Ollama (or DEMO_MOCK_LLM) │
                         │  generate + judge          │
                         └────────────────────────────┘
```

**Processes**

| Process | Port | Role |
|---------|------|------|
| `uvicorn aiflag.api.main:app` | 8010 | Control plane + gate worker |
| `npm run dev` (admin) | 5173 | Ops console (proxies `/api`, `/sdk`) |
| Postgres | 5432 | Flags, events, audit |
| Ollama (optional) | 11434 | Real LLM; mock fallback if down |

**Why 8010?** Sibling projects often bind 8000. Warden defaults the admin proxy and SDK to 8010.

---

## 3. Repository map

```text
src/aiflag/
  api/           FastAPI app, auth, routers
  engine/        evaluate.py (assignment) + gates.py (SLO math)
  workers/       background gate loop
  sdk/           Python client (poll + local eval + event flush)
  demo/          Ollama / mock generate + judge
  models.py      SQLAlchemy tables
  schemas.py     Pydantic request/response models
  seed.py        Dev flags + SDK key
admin/           React + TypeScript ops console
alembic/         Migrations
tests/           Engine, gates, SDK, mock LLM
docs/TUTORIAL.md This document
scripts/         verify_api.py, seed_traffic.py
```

---

## 4. Data model

| Table | Purpose |
|-------|---------|
| `flags` | Key, type (`boolean` \| `multivariate`), status, kill switch, salt |
| `flag_variants` | Variant key, `is_control`, JSON payload |
| `targeting_rules` | Priority, attribute, op (`eq`/`in`/`contains`), value → variant |
| `rollouts` | `percentage_bps` (0–10000), stage, `auto_advance` |
| `quality_slos` | Metric, threshold, min samples, action (`pause`/`rollback`) |
| `sdk_keys` | Hashed client keys |
| `impressions` | Evaluation outcomes |
| `generation_events` | Latency, tokens, errors, model |
| `quality_events` | Judge / thumbs scores |
| `audit_log` | Who changed what |
| `gate_decisions` | Why the worker paused/rolled back/advanced |

**Statuses:** `draft` → `active` → `paused` / `killed`. Kill switch sets status to `killed` and forces control.

**Basis points:** 25% rollout is stored as `2500` so 1% is exact (`100` bps).

---

## 5. Evaluation algorithm (deterministic)

`evaluate(flag, user_key, attributes)` returns `{variant_key, payload, reason, bucket}`:

1. Missing / archived → `FLAG_NOT_FOUND` / `off`
2. `kill_switch` or status `killed` → control, `KILL_SWITCH`
3. Status `paused` or `draft` → control, `FLAG_INACTIVE`
4. First matching targeting rule → that variant, `TARGETING_MATCH`
5. Sticky bucket:

```text
bucket = SHA256(salt + ":" + flag_key + ":" + user_key)[:8] % 10000
if bucket < percentage_bps → treatment (PERCENTAGE_ROLLOUT)
else → control (DEFAULT)
```

Same user always gets the same arm until salt or percentage changes.

**Variant payload example (AI):**

```json
{
  "model": "llama3.2",
  "prompt_id": "support_v2",
  "temperature": 0.2,
  "max_tokens": 640,
  "system_prompt": "You are a cautious support assistant..."
}
```

---

## 6. Gradual rollout & quality gates

**Stages (percent):** `0 → 1 → 5 → 25 → 50 → 100`

**Worker:** every 15 seconds (configurable), for each `active` flag with SLOs:

1. Aggregate treatment vs control in a 15-minute window
2. If either arm has fewer than `min_samples`, skip
3. Else check each SLO; on failure take the strongest action (`rollback` > `pause`)
4. If all pass and `auto_advance=true`, bump to the next stage (with cooldown)

**Default SLOs (seeded on `support_assistant`):**

| Metric | Rule | Action |
|--------|------|--------|
| `error_rate` | treatment − control ≤ 0.05 | pause |
| `latency_p95` | relative increase ≤ 30% | pause |
| `judge_mean` | control − treatment ≤ 0.4 | rollback |
| `tokens_per_request` | treatment / control ≤ 2.0 | pause |

**Kill switch** is manual (or API): everyone gets control immediately, independent of percentage.

---

## 7. APIs

### Auth

- Admin: `Authorization: Bearer <ADMIN_TOKEN>`
- SDK: `Authorization: Bearer <sdk_key>` (hashed in `sdk_keys`)

### Admin / ops

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/overview` | Dashboard flags + recent audit |
| GET | `/api/v1/system/status` | DB, Ollama, mock mode, traffic counts |
| GET/POST | `/api/v1/flags` | List / create |
| GET/PATCH | `/api/v1/flags/{id}` | Detail / update rollout |
| POST | `/api/v1/flags/{id}/publish\|pause\|kill\|restore\|advance` | Lifecycle |
| PUT | `/api/v1/flags/{id}/rules\|variants\|slos` | Replace config |
| GET | `/api/v1/flags/{id}/quality` | Arm metrics + last gate |
| GET | `/api/v1/audit` | Audit trail |
| GET | `/api/v1/gate-decisions` | Gate history |
| POST | `/api/v1/evaluate` | Debug assignment |
| POST | `/api/v1/demo/ask` | Playground ask |
| POST | `/api/v1/demo/simulate` | Batch traffic |
| POST | `/api/v1/demo/thumbs` | Human quality signal |

### SDK

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/sdk/v1/config` | Full flag snapshots for local eval |
| POST | `/sdk/v1/evaluate` | Server-side eval + impression |
| POST | `/sdk/v1/events` | Batch impressions / generations / quality |

OpenAPI: `http://127.0.0.1:8010/docs`

---

## 8. Python SDK

```python
from aiflag.sdk import AIFlags

client = AIFlags(
    sdk_key="sdk_dev_warden_local",
    api_url="http://127.0.0.1:8010",
)

payload = client.variation("support_assistant", user_key="alice")
# use payload["system_prompt"], payload["model"], ...

client.track_generation(
    "support_assistant", "alice", "treatment",
    latency_ms=120, tokens_in=40, tokens_out=80, model="llama3.2",
)
client.track_quality("support_assistant", "alice", "treatment", score=4.5, source="judge")
client.flush()
client.close()
```

**Behavior**

- Polls `/sdk/v1/config` every 10s
- Evaluates **locally** from cache (low latency)
- Fail-open: if the API is down, last cache wins
- Events buffer and flush every poll or at 50 events

---

## 9. Admin UI (how to use the system)

Start the API and admin (see §11), open **http://127.0.0.1:5173**, token `dev-admin-token`.

| Page | What you do |
|------|-------------|
| **Operations** | System health, flag table, recent audit, quick links |
| **Flags** | Browse flags; open detail for rollout / kill / targeting |
| **New flag** | Create boolean or multivariate AI flag and publish |
| **Flag detail** | Slider + stage buttons, auto-advance, variants JSON, rules, SLOs |
| **Quality** | Control vs treatment bars + gate decision log |
| **Playground** | Ask as a user; simulate 24 users to fill metrics |
| **Debugger** | Evaluate any flag/user/attributes; see reason + bucket |
| **Audit** | Full change history |

**Recommended first demo path**

1. Operations → confirm Postgres `ok` (Ollama may be `down` with mock on)
2. Playground → Ask as `alice`, then `bob` (sticky variants)
3. Simulate 24 users → Quality page fills
4. Flag detail → move slider / Advance stage / Kill switch
5. Debugger → confirm `KILL_SWITCH` forces control
6. Restore + Publish → resume rollout

---

## 10. Demo AI loop

`POST /api/v1/demo/ask`:

1. Evaluate `support_assistant` for `user_key`
2. Evaluate `show_confidence` (boolean) — UI may show a confidence pill
3. Call Ollama with the variant system prompt  
   - If Ollama is down and `DEMO_MOCK_LLM=true`, return a variant-aware mock answer
4. Record `generation_events`
5. Judge 1–5 (Ollama or mock), record `quality_events`
6. Optional thumbs from the UI

Seeded flags:

- `support_assistant` — multivariate, 25%, control vs cautious treatment prompts
- `show_confidence` — boolean, 10%

---

## 11. Local setup

### Prerequisites

- Python 3.11+
- Node 18+
- Postgres database `aiflags`
- Optional: [Ollama](https://ollama.com) + `ollama pull llama3.2`

### Install

```powershell
cd "…\AI Featuring Flag System With Gradual Rollout and Quality Monitoring"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` `DATABASE_URL` to match your Postgres user/password. Example used on this machine:

```env
DATABASE_URL=postgresql+psycopg://autopilot:autopilot@127.0.0.1:5432/aiflags
ADMIN_TOKEN=dev-admin-token
DEMO_MOCK_LLM=true
SDK_DEV_KEY=sdk_dev_warden_local
```

```powershell
alembic upgrade head
python -m aiflag.seed
```

### Run

```powershell
uvicorn aiflag.api.main:app --reload --port 8010
```

```powershell
cd admin
npm install
npm run dev
```

### Tests

```powershell
pytest
```

### Helper scripts

```powershell
python scripts\verify_api.py
python scripts\seed_traffic.py
```

---

## 12. Integrating your own app

1. Create an SDK key row (or use the seeded `sdk_dev_warden_local`)
2. Install / import `aiflag.sdk.AIFlags`
3. On each request:

```python
client = AIFlags(sdk_key=..., api_url="http://127.0.0.1:8010")
payload = client.variation("my_ai_flag", user_id)
# call your model with payload
client.track_generation(...)
client.track_quality(..., score=judge_score, source="judge")
```

4. Create the flag in the UI (New flag) or via `POST /api/v1/flags`
5. Watch Quality + Audit while you ramp percentage

---

## 13. Operational playbooks

**Ramp a new prompt safely**

1. Create multivariate flag at 1% or 5%
2. Publish; leave `auto_advance` off until you trust the SLOs
3. Simulate or send real traffic
4. Inspect Quality; Advance stage manually when healthy
5. Only then enable auto-advance

**Something looks bad**

1. Kill switch on the flag (immediate control)
2. Inspect Quality + Audit for the failing metric
3. Fix prompt / model
4. Restore → draft → Publish at a low percentage

**Gates not firing**

- Need enough samples per arm (`min_samples`, default 20)
- Flag must be `active` and not killed
- Worker runs every `GATE_INTERVAL_SECONDS` (15)

---

## 14. Configuration reference

| Env | Default | Meaning |
|-----|---------|---------|
| `DATABASE_URL` | local postgres | SQLAlchemy URL |
| `ADMIN_TOKEN` | `dev-admin-token` | Admin Bearer token |
| `SDK_DEV_KEY` | `sdk_dev_warden_local` | Seeded SDK key plaintext |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | LLM endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Generate model |
| `OLLAMA_JUDGE_MODEL` | `llama3.2` | Judge model |
| `DEMO_MOCK_LLM` | `true` | Mock answers if Ollama down |
| `GATE_ENABLED` | `true` | Background SLO worker |
| `GATE_INTERVAL_SECONDS` | `15` | Worker cadence |
| `GATE_WINDOW_MINUTES` | `15` | Metrics window |

---

## 15. Design choices (why)

- **Local SDK evaluation** — flag checks stay fast; control plane is not on every LLM critical path
- **Sticky hash** — users do not flip variants mid-session when percentage moves slowly
- **Basis points** — exact 1% stages without float drift
- **Simple deltas + min samples** — understandable gates for a portfolio/demo system (not full Bayesian A/B)
- **Mock LLM** — full quality loop without installing Ollama
- **Single Postgres** — no Redis required for v1; config poll is enough

---

## 16. Out of scope (v1)

Multi-tenant orgs, React/JS SDK, Redis streaming, statistical significance tests, prompt CMS, distributed tracing backends, Docker Compose (Postgres is assumed local / existing), cloud LLM providers as first-class (Ollama + mock only).

---

## 17. Quick glossary

| Term | Meaning |
|------|---------|
| Control | Baseline variant |
| Treatment | New AI payload under test |
| Sticky | Same user → same bucket |
| Kill switch | Force control for everyone |
| Gate | Automated SLO check → pause/rollback/advance |
| Impression | Record of an evaluation |
| Judge | LLM (or mock) score 1–5 on an answer |

You now have the mental model, the APIs, the UI workflow, and the ops playbooks to run and extend Warden.
