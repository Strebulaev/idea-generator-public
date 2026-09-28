# Idea Generator

Multi-agent startup idea generation pipeline based on `schema.mermaid`.

## Architecture

Проект разделён на два репозитория:

- **`idea-generator-private`** (приватный) — orchestrator, агенты, промпты `agents/*.yaml`, секреты. Без запускаемых workflow.
- **`idea-generator-public`** (публичный) — poller и GitHub Actions workflow, который выполняется на бесплатных минутах. Содержит минимальный код для запуска пайплайна.

Публичный workflow выполняет весь пайплайн (BS → SCOUT → REVIEWER → ARCH → STRAT → FIN → SYNTH → HITL). При HITL создаются issues в приватном репо.

## Quick start

```bash
# Install
pip install -r requirements.txt

# Run locally
$env:TOPIC="AI tutoring"; $env:DOMAIN="education"; $env:CONSTRAINTS="budget<$50k"; python orchestrator/runner.py
```

## GitHub Actions

Trigger via **Actions → Idea Generator Pipeline → Run workflow** with:
- `topic`
- `domain`
- `constraints` (optional)

Secrets:
- `KILO_GATEWAY_URL` — Kilo Gateway endpoint
- `KILO_API_KEY` — API key for Kilo Gateway
- `IDEA_GENERATOR_MODEL` — model override, defaults to `stepfun/step-3.7-flash:free`
- `QDRANT_URL` — Qdrant endpoint, required for persistent storage
- `QDRANT_API_KEY` — optional, if your Qdrant requires auth

### Storage

- Primary: **Qdrant** via `QDRANT_URL` env var.
- Fallback: GitHub Actions artifacts (`artifacts/<RUN_ID>/`).

### Continuing after HITL

When workflow stops at HITL, you can continue by:
- Adding a comment `GO` / `NO-GO` / `CONFIRM` / `DISPUTE` in the created issue in private repo, or
- Re-running workflow with:
  - `continue_run_id` — the RUN_ID from the stopped run
  - `hitl_decision` — `confirm` or `dispute`

## Components

- `poller.py` — polls Qdrant for pending tasks and dispatches workflow
- `github_client.py` — GitHub API client for workflow and issue management
- `.github/workflows/poller.yml` — cron workflow that runs poller every 5 minutes
- `.github/workflows/pipeline.yml` — main pipeline workflow
- `schema.mermaid` — source of truth for flow
