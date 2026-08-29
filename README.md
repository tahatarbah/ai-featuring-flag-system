# Warden — AI feature flags with gradual rollout and quality monitoring

Control plane for shipping AI changes the way you ship product flags: sticky percentage rollouts, targeting, quality SLOs, auto-pause/rollback, and an instant kill switch. A demo support assistant (Ollama or mock LLM) is gated by the flags so you can watch assignment and quality in the same console.

**Full walkthrough:** [docs/TUTORIAL.md](docs/TUTORIAL.md)

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2, Alembic
- Postgres (local, no Docker required for the app)
- Vite + React admin on `:5173`
- Ollama for the playground (`llama3.2`), with `DEMO_MOCK_LLM=true` fallback

## Setup

Create a Postgres database named `aiflags`, then:

```powershell
cd "C:\Users\Taha\Documents\12 AI projects\AI Featuring Flag System With Gradual Rollout and Quality Monitoring"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` so `DATABASE_URL` matches your local Postgres user/password. Then:

```powershell
alembic upgrade head
python -m aiflag.seed
```

If Ollama is not installed, leave `DEMO_MOCK_LLM=true` (default). The playground still assigns variants, returns mock answers, and records judge scores so quality gates work.

Run the API and admin:

```powershell
uvicorn aiflag.api.main:app --reload --port 8010
```

```powershell
cd admin
npm install
npm run dev
```

Open http://127.0.0.1:5173 — admin token `dev-admin-token`. SDK key `sdk_dev_warden_local`. API on **8010**.

## What to click

1. **Operations** — health, flags at a glance, recent audit.
2. **Flags** / **New flag** — create or open a flag; rollout, publish/pause, kill switch.
3. **Playground** — ask as different users, or **Simulate 24 users**.
4. **Quality** — treatment vs control; gate decisions.
5. **Debugger** — evaluate any user/attributes and see the reason.
6. **Audit** — who killed, advanced, or got rolled back.

## Tests

```powershell
pytest
```

## Layout

- `src/aiflag/engine` — evaluation + SLO math
- `src/aiflag/api` — admin + SDK HTTP
- `src/aiflag/sdk` — local eval client
- `src/aiflag/workers` — quality gate loop
- `src/aiflag/demo` — Ollama / mock LLM
- `admin/` — ops console
- `docs/TUTORIAL.md` — full technical tutorial
