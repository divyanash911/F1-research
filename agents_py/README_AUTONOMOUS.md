# Autonomous F1 Research Corporation (agents_py)

This repo includes an always-on FastAPI service (`agents_py/f1_agents_service`) that can run an autonomous multi-job scheduler to continuously ingest signals and publish new insights for the Next.js site.

## Key ideas

- The service runs **background workers** on startup.
- A SQLite-backed scheduler keeps job state durable across restarts.
- Insights are stored in an append-only JSONL feed (default: `./data/insights.jsonl`).
- The Next.js app proxies the feed at `GET /api/autonomous/insights` and shows it at `/insights`.

## Environment variables

Set these in the repo root `.env.local` (the Python service loads it automatically), or export them in your shell.

- `AUTONOMOUS_ENABLED=1` enables background workers.
- `AUTONOMOUS_STORE_PATH=./data/insights.jsonl` where published bundles are written.
- `AUTONOMOUS_SCHEDULER_DB=./data/autonomous_jobs.sqlite` scheduler DB.
- `AUTONOMOUS_LEASE_SECONDS=300` job lease time.
- `AUTONOMOUS_IDLE_SLEEP_SECONDS=2` worker idle sleep.

LLM config:
- `LLM_PROVIDER=groq` (default)
- `GROQ_API_KEY=...`
- `LLM_MODEL=llama-3.3-70b-versatile`

## API endpoints

- `GET /health`
- `GET /autonomous/status`
- `GET /autonomous/insights?limit=25`
- `GET /autonomous/jobs/recent?limit=50`

## Running locally

From `agents_py/` run the service (example with uvicorn):

```zsh
export AUTONOMOUS_ENABLED=1
export GROQ_API_KEY=YOUR_KEY
uvicorn f1_agents_service.app:app --host 0.0.0.0 --port 8000
```

Then run the Next.js app and open `/insights`.
