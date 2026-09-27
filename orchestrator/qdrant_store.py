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
