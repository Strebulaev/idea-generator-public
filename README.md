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

Trigger via **Actions → Idea Generator → Run workflow** with:
- `topic`
- `domain`
- `constraints` (optional)

Secrets:
- `KILO_GATEWAY_URL` — Kilo Gateway endpoint
- `KILO_API_KEY` — API key for Kilo Gateway
- `IDEA_GENERATOR_MODEL` — model override, defaults to `gpt-4o`

### After secrets are added

1. Commit and push this repo to GitHub.
2. Open **Actions** tab → select **Idea Generator** → **Run workflow**.
3. Fill `topic`, `domain`, optional `constraints`, then click **Run workflow**.
4. Wait for the job to finish.
5. Review the **Step Summary** and download the **Artifacts** (`artifacts/idea-generator-<RUN_ID>/final.json`).

### Continuing after HITL

When workflow stops at HITL, re-run with:
- `continue_run_id` — the RUN_ID from the stopped run
- `hitl_decision` — `confirm` or `dispute`

## Architecture

- `agents/*.yaml` — agent prompts and schemas
- `orchestrator/runner.py` — pipeline execution
- `.github/workflows/idea-generator.yml` — CI entrypoint
- `schema.mermaid` — source of truth for flow
