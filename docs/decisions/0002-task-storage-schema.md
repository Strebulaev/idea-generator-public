---
title: Схема хранения заданий, статусов и отзывов
type: intent
status: active
track: process
created: 2026-09-27
supersedes: null
accepted-by: user
---

# Схема хранения заданий, статусов и отзывов

## Решение

Хранилище — Qdrant, два типа записей:

- `task` — задание на генерацию.
- `event` — событие/отзыв/авто-аппрув по заданию.

## Модель Task

```json
{
  "task_id": "string",
  "run_id": "string",
  "topic": "string",
  "domain": "string",
  "constraints": "string | null",
  "status": "pending | running | awaiting-hitl-1 | awaiting-hitl-2 | awaiting-hitl-3 | succeeded | failed | archived | dead | no-go",
  "current_step": "brainstormer | scout | reviewer | architect | strategist | financier | synthesizer | hitl-1 | hitl-2 | hitl-3 | archive | output",
  "arch_iterations": 0,
  "retry_count": 0,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "finished_at": "ISO-8601 | null",
  "result_ref": "string | null",
  "error": "string | null"
}
```

## Модель Event

```json
{
  "event_id": "string",
  "task_id": "string",
  "run_id": "string",
  "type": "step_start | step_complete | step_error | hitl_created | hitl_decision | hitl_auto_approved | user_feedback | archive | recap",
  "stage": "brainstormer | scout | reviewer | architect | strategist | financier | synthesizer | hitl-1 | hitl-2 | hitl-3 | archive | output",
  "status": "in_process | succeeded | failed",
  "payload": {
    "step": "string",
    "verdict": "GREEN | YELLOW | RED | FIT | NARROW | NO-FIT | VIABLE | TIGHT | DEAD | GO | NO-GO | CONFIRM | DISPUTE",
    "reasoning": "string | null",
    "decision_by": "system | user:<login>",
    "auto_approved": true | false,
    "timeout_seconds": 3600,
    "note": "string | null",
    "issue_url": "string | null",
    "run_id": "string"
  },
  "created_at": "ISO-8601"
}
```

## Правила

- При создании задания создаётся `task` со статусом `pending`.
- При старте шага создаётся `event` типа `step_start` со статусом `in_process`.
- При успехе шага создаётся `event` типа `step_complete` со статусом `succeeded`.
- При ошибке шага создаётся `event` типа `step_error` со статусом `failed`.
- При создании HITL issue создаётся `event` типа `hitl_created` со статусом `in_process`.
- При решении HITL создаётся `event` типа `hitl_decision` со статусом `succeeded`.
- При авто-аппруве создаётся `event` типа `hitl_auto_approved` со статусом `succeeded`.
- При отзыве пользователя создаётся `event` типа `user_feedback` со статусом `succeeded`.
- При архивировании создаётся `event` типа `archive` со статусом `succeeded`.
- При recap-сессии создаётся `event` типа `recap` со статусом `in_process` → `succeeded`.
- `task.status` и `task.current_step` обновляются синхронно с событиями.
- `task.updated_at` обновляется при каждом событии.
- `task.finished_at` заполняется при терминальных статусах: `succeeded`, `failed`, `archived`, `dead`, `no-go`.
- `task.result_ref` заполняется ссылкой на артефакт или issue при терминальном статусе.

## Идентификаторы

- `task_id` — UUID v7 или ULID.
- `event_id` — UUID v7 или ULID.
- `run_id` — `{github_run_id}-{github_run_attempt}` или локальный аналог.

## Публичный доступ

- Публичный poller может читать/писать `task` и `event`.
- Публичный poller не может читать `payload` агентов или промптов.
