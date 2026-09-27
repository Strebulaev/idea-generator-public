import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from orchestrator.qdrant_store import search_ideas, list_run_ideas


def main():
    run_id = os.environ.get("RUN_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
    query = os.environ.get("QDRANT_QUERY", "") or (sys.argv[2] if len(sys.argv) > 2 else "")
    tag = os.environ.get("QDRANT_TAG") or (sys.argv[3] if len(sys.argv) > 3 else None)
    limit = int(os.environ.get("QDRANT_LIMIT", "50"))

    if not run_id:
        print("Usage: RUN_ID=<id> [QUERY] [TAG] python scripts/qdrant_viewer.py")
        sys.exit(1)

    if query or tag:
        ideas = search_ideas(query=query or " ", run_id=run_id, tag=tag, limit=limit)
        print(f"## Идеи по RUN_ID={run_id}, query={query!r}, tag={tag!r}")
    else:
        ideas = list_run_ideas(run_id=run_id)
        print(f"## Идеи по RUN_ID={run_id}")

    if not ideas:
        print("Нет идей.")
        return

    for idea in ideas:
        print(f"- **{idea.get('title')}** [{idea.get('status')}]")
        print(f"  - ID: {idea.get('idea_id')}")
        print(f"  - Теги: {', '.join(idea.get('tags') or [])}")
        print(f"  - Описание: {idea.get('description', '')[:500]}")
        print()


if __name__ == "__main__":
    main()
