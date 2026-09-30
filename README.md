# Idea Generator (Public)

This repository contains the public-facing code for the idea-generator project:
- `poller.py` — polls Qdrant for pending tasks and dispatches workflow
- `github_client.py` — GitHub API client for workflow and issue management
- `.github/workflows/pipeline-steps.yml` — main pipeline workflow
- `.github/workflows/poller.yml` — cron workflow that runs poller every 5 minutes

## Setup

1. Add secrets in repository settings:
   - `KILO_GATEWAY_URL`
   - `KILO_API_KEY`
   - `QDRANT_URL`
   - `QDRANT_API_KEY`
   - `PRIVATE_REPO_TOKEN` — PAT with `contents:read` on `idea-generator-private`
2. Run pipeline via Actions → Idea Generator Pipeline → Run workflow
