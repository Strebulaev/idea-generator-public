# План разработки: генератор стартап-идей (multi-agent pipeline)

## 1. Архитектура на основе schema.mermaid

Система состоит из последовательных агентов и точек принятия решений:

| Узел | Роль | Режим | Выход |
|------|------|-------|-------|
| **START** | Ввод: тема, домен, ограничения | — | Передаёт параметры дальше |
| **BS** (Brainstormer) | recall-first, без критики | Создание | 15–25 идей |
| **SCOUT** | recall-first, без оценки | Исследование | Факты + пробелы по конкурентам, патентам, регуляторике |
| **REVIEWER** | precision-first, оценка выживаемости | Оценка | 🟢 GREEN / 🟡 YELLOW / 🔴 RED |
| **ARCH** (Architect) | recall-first, мутация идеи | Мутация | Изменённая идея (scope, сегмент, модель, юрисдикция) |
| **STRAT** (Strategist) | precision-first | Стратегия | 🟢 FIT / 🟡 NARROW / 🔴 NO-FIT |
| **FIN** (Financier) | precision-first, жёсткий | Финансы | 🟢 VIABLE / 🟡 TIGHT / 🔴 DEAD |
| **SYNTH** (Synthesizer) | Финальное решение | Синтез | one-pager + go/no-go |
| **HITL-2/4/5** | Human-in-the-loop проверки | Валидация | Подтверждение или оспаривание вердикта |
| **ARCHIVE** | Хранилище rejected-идей | Архив | Причина, теги, счётчик пересмотров |

## 2. Запуск на GitHub (GitHub Actions)

### 2.1. Workflow

Файл: `.github/workflows/idea-generator.yml`

**Триггер:** `workflow_dispatch` с параметрами:
- `topic` (обязательный) — тема
- `domain` (обязательный) — домен
- `constraints` (необязательный) — ограничения
- `continue_run_id` (необязательный) — RUN_ID для продолжения после HITL
- `hitl_decision` (необязательный) — решение HITL: `confirm` / `dispute`

**Runner:** `ubuntu-latest`

### 2.2. Переменные окружения

| Переменная | Назначение |
|------------|-----------|
| `KILO_GATEWAY_URL` | URL Kilo Gateway |
| `KILO_API_KEY` | API ключ для доступа к моделям |
| `IDEA_GENERATOR_MODEL` | Модель по умолчанию: `gpt-4o` |
| `GITHUB_TOKEN` | Автоматически предоставляется GitHub Actions |
| `GITHUB_REPOSITORY` | Автоматически предоставляется GitHub Actions |

## 3. Агенты и промпты

Каждый агент описывается в отдельном YAML-файле в `agents/`:

```
agents/
  brainstormer.yaml
  scout.yaml
  reviewer.yaml
  architect.yaml
  strategist.yaml
  financier.yaml
  synthesizer.yaml
  hitl-2.yaml
  hitl-4.yaml
  hitl-5.yaml
```

Каждый файл содержит:
- `id` — уникальный идентификатор узла
- `mode` — `recall-first`, `precision-first` или `human-in-the-loop`
- `system_prompt` — инструкция для модели
- `output_schema` — JSON-схема ожидаемого ответа
- `next` — логика перехода

## 4. Оркестратор

Файл: `orchestrator/runner.py`

Ответственности:
1. Парсинг ввода (`topic`, `domain`, `constraints`)
2. Последовательный вызов агентов через Kilo Gateway API
3. Управление состоянием (`arch_iterations`, verdict history)
4. Маршрутизация по решениям (зелёный/жёлтый/красный)
5. HITL через GitHub Issues (создание issue, ожидание решения, продолжение по `continue_run_id`)
6. Запись артефактов в `artifacts/{run_id}/`
7. Формирование финального one-pager

## 5. Модели

- **Default:** `gpt-4o` (через Kilo Gateway)
- Модель переопределяется через `IDEA_GENERATOR_MODEL` secret

## 6. Хранилище состояния

- JSON-артефакты в `artifacts/{run_id}/`
- При HITL создаётся GitHub Issue с метками `idea-generator`, `hitl`, `awaiting-decision`
- Для продолжения после HITL: повторный запуск workflow с `continue_run_id` и `hitl_decision`

## 7. Структура репозитория

```
idea-generator/
├── .github/
│   └── workflows/
│       └── idea-generator.yml
├── agents/
│   ├── brainstormer.yaml
│   ├── scout.yaml
│   ├── reviewer.yaml
│   ├── architect.yaml
│   ├── strategist.yaml
│   ├── financier.yaml
│   ├── synthesizer.yaml
│   ├── hitl-2.yaml
│   ├── hitl-4.yaml
│   └── hitl-5.yaml
├── orchestrator/
│   ├── runner.py
│   └── summary.py
├── templates/
├── artifacts/ (игнорируется в git)
├── kilo.json
├── plan.md
├── schema.mermaid
└── README.md
```

## 8. Пример вызова workflow

### Первый запуск
```yaml
on:
  workflow_dispatch:
    inputs:
      topic: "AI tutoring"
      domain: "education"
      constraints: "budget<$50k, US only"
```

### Продолжение после HITL
```yaml
on:
  workflow_dispatch:
    inputs:
      continue_run_id: "123456789-1"
      hitl_decision: "dispute"
```

## 9. Пример вызова Kilo API из orchestrator

```python
resp = requests.post(
    f"{KILO_URL}/chat/completions",
    headers={"Authorization": f"Bearer {KILO_API_KEY}"},
    json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": agent_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}},
    },
)
```

## 10. Реализованные решения

1. **HITL:** через GitHub Issues API. При достижении HITL-узла workflow создаёт issue и останавливается. Для продолжения — повторный запуск с `continue_run_id` и `hitl_decision`.
  2. **Модель:** `gpt-4o` по умолчанию, переопределяется через `IDEA_GENERATOR_MODEL` secret.
3. **Kilo:** используется напрямую через Kilo Gateway API из GitHub Actions runner. VS Code extension не требуется.

## 11. Следующие шаги

1. Добавить секреты в GitHub repo settings: `KILO_GATEWAY_URL`, `KILO_API_KEY`, `IDEA_GENERATOR_MODEL`
2. Запустить workflow вручную для теста
3. При необходимости доработать промпты агентов под конкретные результаты
4. Добавить ARCHIVE в базу/файлы при решении `archive`
5. Настроить cron для квартального пересмотра archived-идей
