# Idea Generator

Multi-agent startup idea generation pipeline based on `schema.mermaid`.

## Quick start

```bash
# Install
pip install -r requirements.txt

# Run locally
$env:TOPIC="AI tutoring"; $env:DOMAIN="education"; $env:CONSTRAINTS="budget<$50k"; python orchestrator/runner.py
```

## GitHub Actions

Trigger via **Actions → Idea Generator Pipeline Steps → Run workflow** with:
- `topic`
- `domain`
- `constraints` (optional)

Secrets:
- `KILO_GATEWAY_URL` — Kilo Gateway endpoint
- `KILO_API_KEY` — API key for Kilo Gateway
- `IDEA_GENERATOR_MODEL` — model override, defaults to `stepfun/step-3.7-flash:free`

### Storage

- Primary: **Qdrant** via `QDRANT_URL` env var.
- Fallback: GitHub Actions artifacts (`artifacts/<RUN_ID>/`).

### Continuing after HITL

When workflow stops at HITL, you can continue by:
- Adding a comment `GO` / `NO-GO` / `CONFIRM` / `DISPUTE` in the created issue, or
- Re-running workflow with:
  - `continue_run_id` — the RUN_ID from the stopped run
  - `hitl_decision` — `confirm` or `dispute`

## Architecture

- `agents/*.yaml` — agent prompts and schemas
- `orchestrator/runner.py` — pipeline execution
- `.github/workflows/idea-generator.yml` — CI entrypoint
- `schema.mermaid` — source of truth for flow
