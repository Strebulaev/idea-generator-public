# Idea Generator (Private)

This repository contains the private code for the idea-generator project:
- Orchestrator and pipeline logic
- Agent prompts and schemas
- Qdrant storage configuration

## Structure

```
orchestrator/
  runner.py — pipeline execution
  qdrant_store.py — Qdrant storage
agents/
  *.yaml — agent prompts and schemas
docs/
  decisions/ — architecture decisions
  facts/ — current state facts
  plans/ — implementation plans
schema.mermaid — pipeline flow diagram
requirements.txt — Python dependencies
```

## Running

This repository does not contain runnable workflows. The pipeline is executed in the public repository (`idea-generator-public`) using GitHub Actions.

## Secrets

Secrets are stored in the public repository's GitHub Actions settings:
- `KILO_GATEWAY_URL`
- `KILO_API_KEY`
- `IDEA_GENERATOR_MODEL`
- `QDRANT_URL`
- `QDRANT_API_KEY`

## HITL Issues

Human-in-the-loop issues are created in this repository when the pipeline requires manual intervention.
