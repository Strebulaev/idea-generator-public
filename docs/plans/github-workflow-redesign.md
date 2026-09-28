---
title: План редизайна GitHub Workflow и разделения репозиториев
type: plan
status: draft
track: process
created: 2026-09-27
---

# План редизайна GitHub Workflow и разделения репозиториев

## Цель

Привести текущую архитектуру в соответствие с диаграммой:
- все HITL, кроме после SYNTH, — опциональные с авто-аппрувом через 1h;
- HITL issues создаются в приватном репо;
- всё, требующее запуска gh wf, — в публичном репо (poller + workflow);
- публичный репо используется для экономии минут сборки GitHub Actions.

## Предварительные требования

- Создать два репозитория: `idea-generator-private` и `idea-generator-public`.
- Настроить общий Qdrant, доступный из обоих репо.
- Создать GitHub App / PAT для доступа публичного poller'а к приватному репо (только `issues:write`).

## Шаги

### 1. Подготовить структуру приватного репо

- [ ] Создать репо `idea-generator-private`.
- [ ] Перенести в него: `orchestrator/`, `agents/`, `templates/`, `requirements.txt`, `schema.mermaid`, `README.md` (приватный).
- [ ] Настроить секреты: `KILO_GATEWAY_URL`, `KILO_API_KEY`, `IDEA_GENERATOR_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`.
- [ ] Удалить `.github/workflows/` из приватного репо — workflow не запускаются здесь.
- **Done-when:** `idea-generator-private` содержит orchestrator, agents, промпты, README. Нет workflow, нет runners.

### 2. Подготовить структуру публичного репо

- [ ] Создать репо `idea-generator-public`.
- [ ] Добавить `poller.py`, `github_client.py`.
- [ ] Добавить `.github/workflows/pipeline.yml` — основной workflow, который выполняет пайплайн.
- [ ] Добавить `.github/workflows/poller.yml` — cron, запускающий poller каждые 5 минут.
- [ ] Добавить `README.md` с описанием запуска.
- [ ] Настроить секреты: `PRIVATE_REPO_TOKEN` (`issues:write` в приватном репо), `QDRANT_URL`, `QDRANT_API_KEY`.
- **Done-when:** В публичном репо есть poller, workflow, README. Нет agents/, orchestrator/, промптов.

### 3. Реализовать схему хранения заданий

- [ ] В `qdrant_store.py` добавить коллекции `tasks` и `events` с нужными payload-схемами.
- [ ] Добавить методы: `create_task`, `update_task`, `append_event`, `get_pending_tasks`, `get_task_events`, `get_open_hitl_issues`.
- **Done-when:** `qdrant_store.py` содержит полный CRUD для tasks/events.

### 4. Модифицировать orchestrator для работы с task/event

- [ ] В `runner.py` добавить запись событий в `events` через `emit_event`.
- [ ] Добавить `create_or_update_task` для синхронизации task.
- [ ] Обновить `emit_hitl_issue` для создания issues в приватном репо.
- **Done-when:** `runner.py` пишет все события в Qdrant.

### 5. Реализовать poller в публичном репо

- [ ] Написать `poller.py` с циклом: получить pending задачи → запустить workflow в публичном репо → ждать события → обновить статус.
- [ ] Написать `github_client.py` для запуска workflow и чтения issues в приватном репо.
- [ ] Настроить `.github/workflows/poller.yml` с cron `*/5 * * * *`.
- **Done-when:** Poller запускает workflow в публичном репо, обрабатывает HITL issues в приватном репо, ставит авто-аппрув после 1h.

### 6. Настроить HITL

- [ ] Добавить переменные окружения `HITL1_TIMEOUT_SECONDS`, `HITL2_TIMEOUT_SECONDS` в публичный workflow.
- [ ] Poller проверяет возраст issues, ставит авто-аппрув.
- **Done-when:** При отсутствии решения >1h issue получает комментарий авто-аппрува, пайплайн продолжается.

### 7. Обновить документацию

- [ ] Обновить `README.md` в обоих репо.
- [ ] Обновить `schema.mermaid` если изменилась логика переходов.
- **Done-when:** README описывает новую архитектуру, разделение репо, запуск poller'а.

### 8. Миграция данных

- [ ] Перенести существующие `artifacts/` в новую структуру tasks/events.
- [ ] Создать скрипт миграции `migrate_artifacts_to_qdrant.py`.
- **Done-when:** Все существующие данные доступны через новую схему.

## Критерии приёмки

- Публичный репо не содержит agents/, orchestrator/, промптов.
- Публичный репо содержит workflow, который выполняется на бесплатных минутах.
- Приватный репо содержит код, промпты, секреты. Без workflow.
- Poller запускает workflow в публичном репо.
- HITL issues создаются в приватном репо.
- Авто-аппрув работает для HITL-1 и HITL-2 после 1h таймаута.
- HITL-3 требует ручного решения.
- Все события записываются в Qdrant.
