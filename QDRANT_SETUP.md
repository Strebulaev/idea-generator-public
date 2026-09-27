# Настройка Qdrant

## Вариант A: локально через Docker

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant:latest
```

Проверка:
- API: `curl http://localhost:6333/healthz`
- UI: `http://localhost:6333/dashboard`

## Вариант B: внешний Qdrant для GitHub Actions

1. Зарегистрируйтесь на https://cloud.qdrant.io
2. Создайте cluster
3. Получите URL и API key
4. Добавьте в GitHub Secrets:
   - `QDRANT_URL`
   - `QDRANT_API_KEY`
5. В workflow используйте внешний инстанс, локальный Docker не нужен.

## Переменные окружения

| Переменная | Значение | Где задать |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` или `https://<cluster>.cloud.qdrant.io` | GitHub Secret или env |
| `QDRANT_API_KEY` | API key | GitHub Secret или env |
| `QDRANT_COLLECTION` | `idea_generator` | опционально, по умолчанию `idea_generator` |

## Проверка из Python

```bash
python -c "from qdrant_client import QdrantClient; print(QdrantClient(url='http://localhost:6333').get_collections())"
```

## Workflow

При использовании внешнего Qdrant в `pipeline-steps.yml` задаёте `QDRANT_URL` через секрет и не поднимаете локальный сервис.
