---
title: Текущее состояние архитектуры и реализации
type: fact
status: active
track: process
created: 2026-09-27
---

# Текущее состояние архитектуры и реализации

## Репозиторий

- Один репозиторий `idea-generator` содержит и публичную часть (poller, wf), и приватную (агенты, orchestrator, промпты).
- GitHub Actions workflow находится в `.github/workflows/pipeline-steps.yml`.
- Всё выполняется в публичном репо: runner вызывает `orchestrator/runner.py`, который ходит в Kilo Gateway.

## Workflow

- Workflow `Idea Generator Pipeline Steps` триггерится через `workflow_dispatch`.
- Параметры: `topic`, `domain`, `constraints`, `continue_run_id`, `hitl_decision`.
- Шаги выполняются последовательно в одном job: BS → SCOUT → REVIEWER → ARCH → STRAT → FIN → SYNTH → HITL-5.
- При достижении HITL-2 / HITL-4 / HITL-5 workflow останавливается, создаётся GitHub Issue, continuation возможен через повторный запуск с `continue_run_id`.

## Хранилище

- Артефакты записываются в `artifacts/{run_id}/`.
- Дополнительно поддерживается Qdrant через `orchestrator/qdrant_store.py`.
- `save_record` / `load_record` хранят произвольные ключи по `run_id`.
- `save_idea` / `list_run_ideas` / `search_ideas` хранят идеи в отдельной коллекции.

## Агенты

- `agents/*.yaml` описывают BS, SCOUT, REVIEWER, ARCH, STRAT, FIN, SYNTH, HITL-2, HITL-4, HITL-5.
- Каждый агент имеет `system_prompt`, `output_schema`, `next`.
- Orchestrator загружает агенты через `load_agent`, рендерит промпт через `render_prompt`, вызывает модель через `call_kilo`.

## Ограничения текущей архитектуры

- Весь код в одном репо, включая приватные промпты и agents.
- HITL issues создаются в том же репо, что и код.
- Нет отдельного публичного poller'а; GitHub Actions запускает весь пайплайн сразу.
- Нет централизованной схемы заданий/статусов, кроме файлов `artifacts/{run_id}/state.json`.
- Нет журнала отзывов/авто-аппрувов, привязанного к заданию.
- Нет механизма квартального пересмотра архивов.
