import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from orchestrator.qdrant_store import get_pending_tasks, update_task, append_event
from github_client import create_workflow_dispatch

QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
PRIVATE_REPO_TOKEN = os.environ.get("PRIVATE_REPO_TOKEN", "")

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "pipeline.yml")
WORKFLOW_REF = os.environ.get("WORKFLOW_REF", "main")


def dispatch_pending() -> None:
    tasks = get_pending_tasks(limit=50)
    for task in tasks:
        task_id = task.get("task_id")
        if not task_id:
            continue
        now = datetime.now(timezone.utc).isoformat()
        update_task(task_id, {
            "status": "running",
            "current_step": "brainstormer",
            "updated_at": now,
        })
        append_event({
            "task_id": task_id,
            "run_id": task.get("run_id", task_id),
            "type": "step_start",
            "stage": "brainstormer",
            "status": "in_process",
            "payload": {"task_id": task_id, "step": "brainstormer"},
        })
        inputs = {
            "task_id": task_id,
            "topic": task.get("topic", ""),
            "domain": task.get("domain", ""),
            "constraints": task.get("constraints", ""),
        }
        try:
            create_workflow_dispatch(WORKFLOW_FILE, WORKFLOW_REF, inputs)
        except Exception as exc:
            update_task(task_id, {
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            append_event({
                "task_id": task_id,
                "run_id": task.get("run_id", task_id),
                "type": "step_error",
                "stage": "brainstormer",
                "status": "failed",
                "payload": {"task_id": task_id, "error": str(exc)},
            })


def main() -> None:
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPOSITORY must be set", file=sys.stderr)
        sys.exit(1)
    while True:
        try:
            dispatch_pending()
        except Exception as exc:
            print(f"POLL_ERROR err={exc}", file=sys.stderr)
        if os.environ.get("POLL_ONCE") == "true":
            break
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
