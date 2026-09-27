import os
import json
import uuid
from typing import Any, Optional
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except Exception:
    QDRANT_AVAILABLE = False


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "idea_generator")
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


def _make_point_id(run_id: str, key: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"{run_id}:{key}"))


def save_record(run_id: str, key: str, data: Any) -> None:
    client = ensure_collection()
    payload = {
        "run_id": run_id,
        "key": key,
        "data": data if isinstance(data, dict) else {"value": data},
    }
    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=_make_point_id(run_id, key),
                vector=[0.0],
                payload=payload,
            )
        ],
    )


def load_record(run_id: str, key: str) -> Any | None:
    client = ensure_collection()
    point_id = _make_point_id(run_id, key)
    point = client.retrieve(
        collection_name=QDRANT_COLLECTION,
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


def list_run_keys(run_id: str) -> list[str]:
    client = ensure_collection()
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
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


def save_idea(run_id: str, idea: dict[str, Any]) -> None:
    ideas_collection = os.environ.get("QDRANT_IDEAS_COLLECTION", "ideas")
    client = ensure_collection()
    if not client.collection_exists(ideas_collection):
        client.create_collection(
            collection_name=ideas_collection,
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
    }
    client.upsert(
        collection_name=ideas_collection,
        points=[
            PointStruct(
                id=_make_point_id(run_id, f"idea:{idea_id}"),
                vector=[0.0],
                payload=payload,
            )
        ],
    )


def list_run_ideas(run_id: str) -> list[dict[str, Any]]:
    ideas_collection = os.environ.get("QDRANT_IDEAS_COLLECTION", "ideas")
    client = ensure_collection()
    if not client.collection_exists(ideas_collection):
        return []
    points, _ = client.scroll(
        collection_name=ideas_collection,
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
    ideas_collection = os.environ.get("QDRANT_IDEAS_COLLECTION", "ideas")
    client = ensure_collection()
    if not client.collection_exists(ideas_collection):
        return []
    must_conditions = []
    if run_id:
        must_conditions.append({"key": "run_id", "match": {"value": run_id}})
    if tag:
        must_conditions.append({"key": "tags", "match": {"value": tag}})
    points, _ = client.scroll(
        collection_name=ideas_collection,
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
