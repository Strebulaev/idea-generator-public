---
title: Архитектура публичного poller'а
type: intent
status: active
track: process
created: 2026-09-27
supersedes: null
accepted-by: user
---

# Архитектура публичного poller'а

## Решение

Публичный репо содержит poller и GitHub Actions workflow, который выполняется на бесплатных минутах публичного репо:

1. Poller каждые 5 минут опрашивает базу (Qdrant) на наличие новых заданий со статусом `pending`.
2. Для каждого нового задания:
   - Меняет статус на `running`, создаёт `event` `step_start`.
   - Запускает workflow в **публичном** репо через GitHub API или триггерит его через `workflow_dispatch`.
   - Передаёт `topic`, `domain`, `constraints`, `task_id` как inputs.
3. Workflow в публичном репо выполняет пайплайн (BS → SCOUT → REVIEWER → ARCH → STRAT → FIN → SYNTH → HITL).
4. При достижении HITL пайплайн создаёт issue в **приватном** репо, сохраняет `issue_url` в задании.
5. Poller каждые 5 минут проверяет HITL issues в приватном репо:
   - HITL-1 (опциональный, 1h) — валидация RED.
   - HITL-2 (опциональный, 1h) — проверка DEAD.
   - HITL-3 (обязательный) — финальный go/no-go.
   - Если есть решение — записывает его в базу, продолжает пайплайн.
   - Если таймаут истёк — выполняет авто-аппрув.
6. При завершении задания обновляет `task.status` и `task.finished_at`.

## Компоненты публичного репо

- `poller.py` — основной цикл опроса базы.
- `github_client.py` — обёртка над GitHub API для запуска workflow и работы с issues.
- `.github/workflows/pipeline.yml` — основной workflow, который выполняет пайплайн.
- `.github/workflows/poller.yml` — cron-запуск poller'а каждые 5 минут.

## Секреты публичного репо

- `PRIVATE_REPO_TOKEN` — PAT или GitHub App токен с правами на `issues:write` в приватном репо (для создания HITL issues).
- `QDRANT_URL` — общий Qdrant.
- `QDRANT_API_KEY` — опционально.

## Запуск workflow

```python
# poller запускает workflow в публичном репо
github_client.create_workflow_dispatch(
    repo="org/idea-generator-public",
    workflow="pipeline.yml",
    ref="main",
    inputs={"task_id": task_id, "topic": topic, "domain": domain, "constraints": constraints},
)
```

## Обоснование

- Публичный репо используется для экономии минут сборки GitHub Actions: минуты в публичном репо не ограничены.
- Приватный репо хранит код, промпты и секреты, но не запускает workflow.
- Публичный poller — единственный компонент, которому нужен доступ к GitHub API приватного репо, и только для создания HITL issues.
- Публичный репо не знает о промптах и внутренней архитектуре пайплайна.
- Cron в публичном репо обеспечивает регулярную проверку базы без раскрытия внутренней логики.

## Исключения

- Если публичный репо недоступен, poller ставит задание в `failed` с ошибкой.
- Если Qdrant недоступен, poller логирует ошибку и продолжает цикл.
