import os
import json
import uuid
from typing import Any, Optional
from datetime import datetime, timezone

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except Exception:
    QDRANT_AVAILABLE = False


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "idea_generator")
STATE_COLLECTION = os.environ.get("QDRANT_STATE_COLLECTION", "idea_generator_state")
TASKS_COLLECTION = os.environ.get("QDRANT_TASKS_COLLECTION", "tasks")
EVENTS_COLLECTION = os.environ.get("QDRANT_EVENTS_COLLECTION", "events")
IDEAS_COLLECTION = os.environ.get("QDRANT_IDEAS_COLLECTION", "ideas")
ID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def get_client() -> "QdrantClient":
    if not QDRANT_AVAILABLE:
        raise RuntimeError("qdrant_client package is not installed")
    if QDRANT_API_KEY:
        return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: Optional["QdrantClient"] = None) -> "QdrantClient":
    if client is None:
        client = get_client()
    if not client.collection_exists(QDRANT_COLLECTION):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    return client


def ensure_state_collection(client: Optional["QdrantClient"] = None) -> "QdrantClient":
    if client is None:
        client = get_client()
    if not client.collection_exists(STATE_COLLECTION):
        client.create_collection(
            collection_name=STATE_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    return client


def ensure_tasks_collection(client: Optional["QdrantClient"] = None) -> "QdrantClient":
    if client is None:
        client = get_client()
    if not client.collection_exists(TASKS_COLLECTION):
        client.create_collection(
            collection_name=TASKS_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    return client


def ensure_events_collection(client: Optional["QdrantClient"] = None) -> "QdrantClient":
    if client is None:
        client = get_client()
    if not client.collection_exists(EVENTS_COLLECTION):
        client.create_collection(
            collection_name=EVENTS_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    return client


def _make_point_id(run_id: str, key: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"{run_id}:{key}"))


def _make_state_point_id(run_id: str, key: str) -> str:
    return f"state:{run_id}:{key}"


def _make_idea_point_id(run_id: str, idea_id: str) -> str:
    return f"idea:{run_id}:{idea_id}"


def _make_task_point_id(task_id: str) -> str:
    return f"task:{task_id}"


def _make_event_point_id(event_id: str) -> str:
    return f"event:{event_id}"


def save_record(run_id: str, key: str, data: Any) -> None:
    client = ensure_state_collection()
    payload = {
        "run_id": run_id,
        "key": key,
        "type": "state",
        "data": data if isinstance(data, dict) else {"value": data},
    }
    client.upsert(
        collection_name=STATE_COLLECTION,
        points=[
            PointStruct(
                id=_make_state_point_id(run_id, key),
                vector=[0.0],
                payload=payload,
            )
        ],
    )


def load_record(run_id: str, key: str) -> Any | None:
    client = ensure_state_collection()
    point_id = _make_state_point_id(run_id, key)
    point = client.retrieve(
        collection_name=STATE_COLLECTION,
        ids=[point_id],
    )
    if not point:
        return None
    payload = point[0].payload
    if not payload:
        return None
    data = payload.get("data", {})
    if isinstance(data, dict) and "value" in data and len(data) == 1:
        return data["value"]
    return data


def save_idea(run_id: str, idea: dict[str, Any]) -> None:
    client = ensure_collection()
    if not client.collection_exists(IDEAS_COLLECTION):
        client.create_collection(
            collection_name=IDEAS_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    idea_id = idea.get("id") or idea.get("idea_id") or str(uuid.uuid4())
    title = idea.get("title", "")
    description = idea.get("description", "")
    tags = idea.get("tags") or []
    payload = {
        "run_id": run_id,
        "idea_id": str(idea_id),
        "title": title,
        "description": description,
        "tags": tags,
        "source": idea.get("source") or "brainstormer",
        "status": idea.get("status") or "new",
        "type": "idea",
    }
    client.upsert(
        collection_name=IDEAS_COLLECTION,
        points=[
            PointStruct(
                id=_make_idea_point_id(run_id, str(idea_id)),
                vector=[0.0],
                payload=payload,
            )
        ],
    )


def list_run_keys(run_id: str) -> list[str]:
    client = ensure_state_collection()
    points, _ = client.scroll(
        collection_name=STATE_COLLECTION,
        scroll_filter={
            "must": [
                {
                    "key": "run_id",
                    "match": {"value": run_id},
                }
            ]
        },
        limit=1000,
    )
    keys = []
    for p in points:
        payload = p.payload or {}
        key = payload.get("key")
        if key:
            keys.append(key)
    return sorted(keys)


def list_run_ideas(run_id: str) -> list[dict[str, Any]]:
    client = ensure_collection()
    if not client.collection_exists(IDEAS_COLLECTION):
        return []
    points, _ = client.scroll(
        collection_name=IDEAS_COLLECTION,
        scroll_filter={
            "must": [
                {
                    "key": "run_id",
                    "match": {"value": run_id},
                }
            ]
        },
        limit=1000,
    )
    ideas = []
    for p in points:
        payload = p.payload or {}
        ideas.append(
            {
                "idea_id": payload.get("idea_id"),
                "title": payload.get("title"),
                "description": payload.get("description"),
                "tags": payload.get("tags") or [],
                "source": payload.get("source"),
                "status": payload.get("status"),
            }
        )
    return ideas


def search_ideas(query: str, run_id: str | None = None, tag: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    client = ensure_collection()
    if not client.collection_exists(IDEAS_COLLECTION):
        return []
    must_conditions = []
    if run_id:
        must_conditions.append({"key": "run_id", "match": {"value": run_id}})
    if tag:
        must_conditions.append({"key": "tags", "match": {"value": tag}})
    points, _ = client.scroll(
        collection_name=IDEAS_COLLECTION,
        scroll_filter={"must": must_conditions} if must_conditions else None,
        limit=limit,
    )
    query_lower = query.lower()
    results = []
    for p in points:
        payload = p.payload or {}
        text = f"{payload.get('title', '')} {payload.get('description', '')} {' '.join(payload.get('tags') or [])}".lower()
        if query_lower in text:
            results.append(
                {
                    "idea_id": payload.get("idea_id"),
                    "title": payload.get("title"),
                    "description": payload.get("description"),
                    "tags": payload.get("tags") or [],
                    "source": payload.get("source"),
                    "status": payload.get("status"),
                }
            )
    return results


def create_task(task: dict[str, Any]) -> None:
    client = ensure_tasks_collection()
    task_id = task.get("task_id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "task_id": task_id,
        "run_id": task.get("run_id", ""),
        "topic": task.get("topic", ""),
        "domain": task.get("domain", ""),
        "constraints": task.get("constraints"),
        "status": task.get("status", "pending"),
        "current_step": task.get("current_step", "brainstormer"),
        "arch_iterations": task.get("arch_iterations", 0),
        "retry_count": task.get("retry_count", 0),
        "created_at": task.get("created_at", now),
        "updated_at": now,
        "finished_at": task.get("finished_at"),
        "result_ref": task.get("result_ref"),
        "error": task.get("error"),
    }
    client.upsert(
        collection_name=TASKS_COLLECTION,
        points=[
            PointStruct(
                id=_make_task_point_id(task_id),
                vector=[0.0],
                payload=payload,
            )
        ],
    )
    task["task_id"] = task_id


def update_task(task_id: str, updates: dict[str, Any]) -> None:
    client = ensure_tasks_collection()
    point_id = _make_task_point_id(task_id)
    point = client.retrieve(
        collection_name=TASKS_COLLECTION,
        ids=[point_id],
    )
    if not point:
        raise ValueError(f"Task not found: {task_id}")
    payload = dict(point[0].payload or {})
    payload.update(updates)
    if "updated_at" not in updates:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert(
        collection_name=TASKS_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=[0.0],
                payload=payload,
            )
        ],
    )


def append_event(event: dict[str, Any]) -> None:
    client = ensure_events_collection()
    event_id = event.get("event_id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": event_id,
        "task_id": event.get("task_id", ""),
        "run_id": event.get("run_id", ""),
        "type": event.get("type", "step_complete"),
        "stage": event.get("stage", ""),
        "status": event.get("status", "succeeded"),
        "payload": event.get("payload", {}),
        "created_at": event.get("created_at", now),
    }
    client.upsert(
        collection_name=EVENTS_COLLECTION,
        points=[
            PointStruct(
                id=_make_event_point_id(event_id),
                vector=[0.0],
                payload=payload,
            )
        ],
    )
    event["event_id"] = event_id


def get_pending_tasks(limit: int = 50) -> list[dict[str, Any]]:
    client = ensure_tasks_collection()
    points, _ = client.scroll(
        collection_name=TASKS_COLLECTION,
        scroll_filter={
            "must": [
                {
                    "key": "status",
                    "match": {"value": "pending"},
                }
            ]
        },
        limit=limit,
    )
    tasks = []
    for p in points:
        payload = p.payload or {}
        tasks.append(dict(payload))
    return tasks


def get_task_events(task_id: str, limit: int = 200) -> list[dict[str, Any]]:
    client = ensure_events_collection()
    points, _ = client.scroll(
        collection_name=EVENTS_COLLECTION,
        scroll_filter={
            "must": [
                {
                    "key": "task_id",
                    "match": {"value": task_id},
                }
            ]
        },
        limit=limit,
    )
    events = []
    for p in points:
        payload = p.payload or {}
        events.append(dict(payload))
    events.sort(key=lambda e: e.get("created_at", ""))
    return events


def get_tasks_by_status(statuses: list[str], limit: int = 50) -> list[dict[str, Any]]:
    client = ensure_tasks_collection()
    scroll_filter = {
        "should": [
            {"key": "status", "match": {"value": status}}
            for status in statuses
        ]
    }
    points, _ = client.scroll(
        collection_name=TASKS_COLLECTION,
        scroll_filter=scroll_filter,
        limit=limit,
    )
    tasks = []
    for p in points:
        payload = p.payload or {}
        tasks.append(dict(payload))
    return tasks


def get_open_hitl_issues(task_id: str | None = None, hitl_type: str | None = None) -> list[dict[str, Any]]:
    client = ensure_events_collection()
    must_conditions = [
        {"key": "type", "match": {"value": "hitl_created"}},
    ]
    if task_id:
        must_conditions.append({"key": "task_id", "match": {"value": task_id}})
    if hitl_type:
        must_conditions.append({"key": "stage", "match": {"value": hitl_type}})
    points, _ = client.scroll(
        collection_name=EVENTS_COLLECTION,
        scroll_filter={"must": must_conditions},
        limit=100,
    )
    results = []
    for p in points:
        payload = p.payload or {}
        results.append(dict(payload))
    return results
