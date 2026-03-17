# f1-agents (Python)

A small Python service that hosts **tool-using LangGraph agents** for the F1 Intelligence Platform.

## What you get

- **LangGraph ReAct-style agent loop** (LLM decides when to call tools)
- Tools:
  - OpenF1 API wrappers (sessions, meetings, results)
  - Web search (DuckDuckGo)
  - Persistent knowledge base (simple JSONL memory)
- **FastAPI** HTTP server so your Next.js app can call agents without embedding secrets in Node.

## Setup

Create a virtual env (recommended) and install deps:

```bash
cd agents_py
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Set environment variables:

- `OPENROUTER_API_KEY` (or `OPENAI_API_KEY` if you choose to swap providers)
- Optional: `AGENTS_KB_PATH` (defaults to `./data/kb.jsonl`)

## Run

```bash
cd agents_py
source .venv/bin/activate
uvicorn f1_agents_service.app:app --host 0.0.0.0 --port 8001 --reload
```

Then call:

- `POST http://localhost:8001/agent/run`

## Notes on “chain-of-thought”

This service **does not return chain-of-thought**. The agent uses internal reasoning to decide on tool calls, but only returns a concise answer + citations and tool traces suitable for debugging.
