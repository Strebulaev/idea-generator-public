import re
import os
import sys
import json
import time
import traceback
import yaml
import requests
import base64
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

RUN_ID = os.environ.get("RUN_ID", f"local-{int(time.time())}")
STEP_NAME = os.environ.get("STEP_NAME", "")
TOPIC = os.environ.get("TOPIC", "")
DOMAIN = os.environ.get("DOMAIN", "")
CONSTRAINTS = os.environ.get("CONSTRAINTS", "")
KILO_URL = os.environ.get("KILO_GATEWAY_URL", "https://gateway.kilo.ai/v1")
KILO_API_KEY = os.environ.get("KILO_API_KEY", "")
MODEL = os.environ.get("GITHUB_MODEL", "gpt-4o")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CONTINUE_RUN_ID = os.environ.get("CONTINUE_RUN_ID", "")
HITL_DECISION = os.environ.get("HITL_DECISION", "")
HITL1_TIMEOUT_SECONDS = int(os.environ.get("HITL1_TIMEOUT_SECONDS", "3600"))
HITL2_TIMEOUT_SECONDS = int(os.environ.get("HITL2_TIMEOUT_SECONDS", "3600"))
QDRANT_ENABLED = bool(os.environ.get("QDRANT_URL"))

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
AGENTS_DIR = BASE_DIR / "agents"
ARTIFACTS_DIR = BASE_DIR / "artifacts" / RUN_ID
TEMPLATES_DIR = BASE_DIR / "templates"
STATE_FILE = ARTIFACTS_DIR / "state.json"

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

from orchestrator.qdrant_store import (
    save_record,
    load_record,
    list_run_keys,
    ensure_collection,
    save_idea,
    list_run_ideas,
    search_ideas,
    ensure_collection,
    create_task,
    update_task,
    append_event,
    get_pending_tasks,
    get_task_events,
    get_open_hitl_issues,
)


def gh_request(method, path, **kwargs):
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    headers["Accept"] = "application/vnd.github+json"
    resp = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    resp.raise_for_status()
    if resp.status_code == 204:
        return None
    return resp.json()


def download_previous_artifacts(run_id: str) -> Path:
    target = BASE_DIR / "artifacts" / "_continued"
    target.mkdir(parents=True, exist_ok=True)
    data = gh_request("GET", f"/actions/runs/{run_id}/artifacts")
    if not data or "artifacts" not in data:
        raise RuntimeError(f"No artifacts found for run {run_id}")
    artifact = data["artifacts"][0]
    archive_url = artifact["archive_download_url"]
    resp = requests.get(archive_url, headers={"Authorization": f"Bearer {GITHUB_TOKEN}"}, timeout=120)
    resp.raise_for_status()
    zip_path = target / "artifact.zip"
    zip_path.write_bytes(resp.content)
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)
    zip_path.unlink(missing_ok=True)
    return target


def create_github_issue(title, body, labels=None):
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    return gh_request("POST", "/issues", json=payload)


def load_agent(agent_id: str) -> dict:
    path = AGENTS_DIR / f"{agent_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_prompt(template: str, context: dict[str, Any]) -> str:
    for key, value in context.items():
        if value is None:
            value = ""
        template = template.replace("{{" + key + "}}", str(value))
    return template


def extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_kilo(system_prompt: str, user_prompt: str, response_schema: dict | None = None) -> dict:
    if not KILO_API_KEY:
        print("ERROR: KILO_API_KEY is not set", file=sys.stderr)
        raise RuntimeError("KILO_API_KEY is not set")

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    if response_schema:
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": response_schema}}

    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{KILO_URL}/chat/completions",
                headers={"Authorization": f"Bearer {KILO_API_KEY}"},
                json=payload,
                timeout=(20, 180),
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                return extract_json(content)
            except Exception as exc:
                print(f"KILO_JSON_PARSE_ERROR attempt={attempt+1} model={MODEL} err={exc}", file=sys.stderr)
                return {"raw": content}
        except requests.exceptions.ReadTimeout as exc:
            last_exc = exc
            print(f"KILO_TIMEOUT attempt={attempt+1} model={MODEL} url={KILO_URL}", file=sys.stderr)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            print(f"KILO_HTTP_ERROR status={status} attempt={attempt+1} model={MODEL} url={KILO_URL}", file=sys.stderr)
            raise
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            print(f"KILO_CONNECTION_ERROR attempt={attempt+1} model={MODEL} url={KILO_URL} err={exc}", file=sys.stderr)
        except Exception as exc:
            last_exc = exc
            print(f"KILO_UNEXPECTED_ERROR attempt={attempt+1} model={MODEL} err={exc}", file=sys.stderr)
        time.sleep(min(60, 5 * (attempt + 1)))

    raise last_exc


def save_artifact(name: str, data: dict | str) -> Path:
    path = ARTIFACTS_DIR / f"{name}.json"
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        def _default(o):
            try:
                return repr(o)
            except Exception:
                return f"<non-serializable:{getattr(o, '__class__', type(o)).__name__}>"

        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=_default), encoding="utf-8"
        )
    if QDRANT_ENABLED:
        try:
            save_record(RUN_ID, name, data)
        except Exception as exc:
            print(f"QDRANT_SAVE_ERROR key={name} err={exc}", file=sys.stderr)
    return path


def load_artifact(name: str) -> Any:
    if QDRANT_ENABLED:
        try:
            data = load_record(RUN_ID, name)
            if data is not None:
                return data
        except Exception as exc:
            print(f"QDRANT_LOAD_ERROR key={name} err={exc}", file=sys.stderr)
    path = ARTIFACTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def save_state(state: dict[str, Any]) -> None:
    save_artifact("state", state)


def load_state() -> dict[str, Any]:
    data = load_artifact("state")
    if isinstance(data, dict):
        return data
    return {}


def emit_event(event_type: str, stage: str, payload: dict[str, Any]) -> None:
    if not QDRANT_ENABLED:
        return
    try:
        event = {
            "event_id": str(__import__("uuid").uuid4()),
            "task_id": RUN_ID,
            "run_id": RUN_ID,
            "type": event_type,
            "stage": stage,
            "status": "succeeded" if event_type in ("step_complete", "hitl_decision", "hitl_auto_approved", "archive", "recap") else "in_process",
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        append_event(event)
    except Exception as exc:
        print(f"QDRANT_EVENT_ERROR type={event_type} err={exc}", file=sys.stderr)


def create_or_update_task(state: dict[str, Any]) -> None:
    if not QDRANT_ENABLED:
        return
    try:
        task = {
            "task_id": RUN_ID,
            "run_id": RUN_ID,
            "topic": state.get("topic", ""),
            "domain": state.get("domain", ""),
            "constraints": state.get("constraints"),
            "status": state.get("status", "pending"),
            "current_step": state.get("current_step", STEP_NAME or "brainstormer"),
            "arch_iterations": state.get("arch_iterations", 0),
            "retry_count": state.get("retry_count", 0),
            "created_at": state.get("started_at", datetime.now(timezone.utc).isoformat()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": state.get("finished_at"),
            "result_ref": state.get("result_ref"),
            "error": state.get("error"),
        }
        create_task(task)
    except Exception as exc:
        print(f"QDRANT_TASK_ERROR err={exc}", file=sys.stderr)


def emit_hitl_issue(hitl_id: str, state: dict[str, Any], prompt_text: str, options: list[str]) -> dict:
    current_idea = state.get("current_idea") or state.get("mutated_idea") or (state.get("ideas", [{}])[0])
    idea_block = ""
    if current_idea:
        idea_block = f"""### 💡 Идея
- **ID:** {current_idea.get('id', '-')}
- **Название:** {current_idea.get('title', '-')}
- **Описание:** {current_idea.get('description', '-')}
- **Теги:** {', '.join(current_idea.get('tags', []) or [])}
"""

    risks = state.get("risks") or []
    risks_block = ""
    if risks:
        risks_block = "### ⚠️ Риски\n" + "\n".join([f"- {r}" for r in risks]) + "\n"

    prompt_block = f"### 🧠 Запрос\n{prompt_text}\n"
    options_block = "### 🎯 Варианты\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)]) + "\n"

    timeout_seconds = HITL1_TIMEOUT_SECONDS if hitl_id == "HITL-1" else HITL2_TIMEOUT_SECONDS if hitl_id == "HITL-2" else 0
    timeout_info = f"\n\n⏰ Авто-аппрув через {timeout_seconds} секунд при отсутствии решения." if timeout_seconds else "\n\n⚠️ Это обязательный шаг, авто-аппрув не применяется."

    context_block = f"""### 📌 Контекст
- **RUN_ID:** {RUN_ID}
- **Хэш workflow run:** {GITHUB_REPOSITORY}/actions/runs/{RUN_ID}
- **Тема:** {state.get('topic', '-')}
- **Домен:** {state.get('domain', '-')}
- **Ограничения:** {state.get('constraints', '-') or '-'}
{timeout_info}
"""

    body = "\n".join([context_block, idea_block, risks_block, prompt_block, options_block])

    issue_title = f"[HITL] {hitl_id} — требуется решение для RUN_ID={RUN_ID}"
    labels = ["idea-generator", "hitl", "awaiting-decision"]
    if hitl_id == "HITL-3":
        labels.append("required")
    issue = create_github_issue(issue_title, body, labels=labels)
    issue_url = issue.get("html_url") if issue else ""
    print(f"HITL issue created: {issue_url}")
    if QDRANT_ENABLED:
        try:
            emit_event(
                "hitl_created",
                hitl_id.lower().replace("hitl-", "hitl_").replace("-", "_"),
                {
                    "issue_url": issue_url,
                    "hitl_id": hitl_id,
                    "prompt": prompt_text,
                    "options": options,
                    "timeout_seconds": timeout_seconds,
                    "auto_approved": bool(timeout_seconds),
                },
            )
        except Exception as exc:
            print(f"QDRANT_EVENT_ERROR hitl_created err={exc}", file=sys.stderr)
    return issue or {}


def step(name: str, agent_id: str, context: dict[str, Any]) -> dict:
    print(f"[STEP] {name} -> agent={agent_id}")
    if QDRANT_ENABLED:
        try:
            emit_event("step_start", name, {"step": name, "agent": agent_id})
        except Exception as exc:
            print(f"QDRANT_EVENT_ERROR step_start err={exc}", file=sys.stderr)
    agent = load_agent(agent_id)
    system_prompt = render_prompt(agent["system_prompt"], context)
    user_prompt = json.dumps(context, ensure_ascii=False)
    result = call_kilo(system_prompt, user_prompt, agent.get("output_schema"))
    save_artifact(name, result)
    if QDRANT_ENABLED:
        try:
            emit_event("step_complete", name, {"step": name, "agent": agent_id})
        except Exception as exc:
            print(f"QDRANT_EVENT_ERROR step_complete err={exc}", file=sys.stderr)
    return result


def _extract_ideas_from_result(result: Any) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    if isinstance(result, dict):
        raw_ideas = result.get("ideas")
        if isinstance(raw_ideas, list):
            for idea in raw_ideas:
                if isinstance(idea, dict):
                    ideas.append({
                        "id": str(idea.get("id") or idea.get("idea_id") or ""),
                        "title": str(idea.get("title") or ""),
                        "description": str(idea.get("description") or ""),
                        "tags": idea.get("tags") or [],
                    })
            if ideas:
                return ideas
        if result.get("title") or result.get("description"):
            ideas.append({
                "id": str(result.get("id") or result.get("idea_id") or ""),
                "title": str(result.get("title") or ""),
                "description": str(result.get("description") or ""),
                "tags": result.get("tags") or [],
            })
            return ideas
    return ideas


def run_brainstormer(state: dict[str, Any]) -> dict[str, Any]:
    result = step("01_brainstormer", "brainstormer", state)
    state["ideas"] = _extract_ideas_from_result(result)
    if len(state["ideas"]) < 15:
        print(f"Brainstormer returned {len(state['ideas'])} ideas, requesting more to reach 15...", file=sys.stderr)
        for expand_attempt in range(3):
            expand_prompt = (
                f"Сгенерируй СТРОГО 15-25 идей по теме: {state.get('topic')}, домен: {state.get('domain')}, "
                f"ограничения: {state.get('constraints') or '-'}. "
                f"Верни ТОЛЬКО JSON {{'ideas': [...]}} с полями id, title, description, tags. "
                f"БЕЗ пояснений, БЕЗ markdown, БЕЗ ```json```. "
                f"Минимум 15 идей, максимум 25."
            )
            expand_result = call_kilo(
                "Ты — мозговой штурм-агент. Сгенерируй 15-25 идей. ТОЛЬКО JSON.",
                expand_prompt,
                {
                    "type": "object",
                    "properties": {
                        "ideas": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["id", "title", "description", "tags"],
                            },
                        },
                    },
                    "required": ["ideas"],
                },
            )
            expanded = _extract_ideas_from_result(expand_result)
            if len(expanded) >= 15:
                existing_ids = {idea.get("id") for idea in state["ideas"]}
                for idea in expanded:
                    idea_id = idea.get("id")
                    if idea_id not in existing_ids:
                        state["ideas"].append(idea)
                        existing_ids.add(idea_id)
                break
            print(f"Expansion attempt {expand_attempt+1} returned {len(expanded)} ideas, retrying...", file=sys.stderr)
        save_artifact("01_brainstormer_expanded", {"ideas": state["ideas"]})
    if not state["ideas"]:
        print("ERROR: Brainstormer returned no ideas", file=sys.stderr)
        print("Brainstormer raw result: " + json.dumps(result, ensure_ascii=False)[:2000], file=sys.stderr)
        raise RuntimeError("Brainstormer returned no ideas")
    state["current_idea"] = state["ideas"][0]
    if QDRANT_ENABLED:
        try:
            for idea in state["ideas"]:
                save_idea(RUN_ID, idea)
        except Exception as exc:
            print(f"QDRANT_IDEAS_SAVE_ERROR err={exc}", file=sys.stderr)
    return state


def run_scout(state: dict[str, Any]) -> dict[str, Any]:
    result = step("02_scout", "scout", state)
    state["scout_data"] = result.get("research", [])
    return state


def run_reviewer(state: dict[str, Any]) -> dict[str, Any]:
    result = step("03_reviewer", "reviewer", state)
    verdicts = result.get("verdicts", [])
    verdict = verdicts[0]["verdict"] if verdicts else "YELLOW"
    state["reviewer_verdict"] = verdict
    state["reviewer_reasoning"] = verdicts[0].get("reasoning", "") if verdicts else ""
    state["risks"] = verdicts[0].get("risks", []) if verdicts else []
    return state


def run_architect(state: dict[str, Any]) -> dict[str, Any]:
    result = step("04_architect", "architect", state)
    state["mutated_idea"] = result.get("mutated_idea", state.get("current_idea"))
    state["arch_iterations"] = result.get("arch_iterations", state.get("arch_iterations", 0) + 1)
    state["current_idea"] = state["mutated_idea"]
    return state


def run_strategist(state: dict[str, Any]) -> dict[str, Any]:
    result = step("05_strategist", "strategist", state)
    state["strategy"] = result
    return state


def run_financier(state: dict[str, Any]) -> dict[str, Any]:
    result = step("06_financier", "financier", state)
    state["finances"] = result
    return state


def run_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
    result = step("07_synthesizer", "synthesizer", state)
    state["synthesis"] = result
    state["status"] = "ready-for-hitl-5"
    return state


def run_hitl_1(state: dict[str, Any]) -> dict[str, Any]:
    result = step("hitl-1", "hitl-1", state)
    emit_hitl_issue(
        "HITL-1",
        state,
        result.get("hitl_prompt", "Reviewer вынес RED. Подтвердить?"),
        result.get("options", ["Подтверждаю RED", "Оспариваю"]),
    )
    state["status"] = "awaiting-hitl-1"
    return state


def run_hitl_2(state: dict[str, Any]) -> dict[str, Any]:
    result = step("hitl-2", "hitl-2", state)
    emit_hitl_issue(
        "HITL-2",
        state,
        result.get("hitl_prompt", "Финансы показали DEAD. Подтвердить?"),
        result.get("options", ["Подтверждаю DEAD", "Оспариваю"]),
    )
    state["status"] = "awaiting-hitl-2"
    return state


def run_hitl_3(state: dict[str, Any]) -> dict[str, Any]:
    result = step("hitl-3", "hitl-3", state)
    emit_hitl_issue(
        "HITL-3",
        state,
        result.get("hitl_prompt", "Финальное решение: GO или NO-GO?"),
        result.get("options", ["GO", "NO-GO"]),
    )
    state["status"] = "awaiting-hitl-3"
    return state


ROUTER = {
    "brainstormer": run_brainstormer,
    "scout": run_scout,
    "reviewer": run_reviewer,
    "architect": run_architect,
    "strategist": run_strategist,
    "financier": run_financier,
    "synthesizer": run_synthesizer,
    "hitl-1": run_hitl_1,
    "hitl-2": run_hitl_2,
    "hitl-3": run_hitl_3,
    "qdrant-healthcheck": None,
}


def qdrant_healthcheck(state: dict[str, Any]) -> dict[str, Any]:
    print("QDRANT_URL=" + os.environ.get("QDRANT_URL", ""), file=sys.stderr)
    if QDRANT_ENABLED:
        try:
            ensure_collection()
        except Exception as exc:
            print(f"QDRANT_HEALTHCHECK_ERROR err={exc}", file=sys.stderr)
    return state


ROUTER["qdrant-healthcheck"] = qdrant_healthcheck


def continue_after_hitl(state: dict[str, Any]) -> dict[str, Any]:
    status = state.get("status", "")
    decision = (HITL_DECISION or "").lower()

    if status == "awaiting-hitl-1":
        if decision == "dispute":
            state["hitl_decision"] = "disputed"
            emit_event("hitl_decision", "hitl-1", {"decision": "disputed", "hitl_id": "HITL-1"})
            state = run_scout(state)
            save_state(state)
            state = run_reviewer(state)
            save_state(state)
            verdict = state.get("reviewer_verdict", "YELLOW")
            if verdict == "RED":
                state = run_hitl_1(state)
                save_state(state)
                return state
            if verdict == "YELLOW":
                state = run_post_arch_loop(state)
                if state.get("status") in ("archived", "awaiting-hitl-1", "awaiting-hitl-2", "awaiting-hitl-3", "succeeded", "failed"):
                    return state
            state = run_strategist(state)
            save_state(state)
            strat_result = state.get("strategy", {})
            strat_verdict = strat_result.get("verdict", "FIT") if isinstance(strat_result, dict) else "FIT"
            if strat_verdict in ("NO-FIT",):
                state["status"] = "archived"
                state["finished_at"] = datetime.now(timezone.utc).isoformat()
                save_state(state)
                emit_event("archive", "archive", {"reason": f"STRAT verdict={strat_verdict}"})
                return state
            state = run_financier(state)
            save_state(state)
            if state.get("finances", {}).get("verdict") == "DEAD":
                state = run_hitl_2(state)
                save_state(state)
                return state
            state = run_synthesizer(state)
            save_state(state)
            state = run_hitl_3(state)
            save_state(state)
            return state
        else:
            state["hitl_decision"] = "confirmed"
            emit_event("hitl_decision", "hitl-1", {"decision": "confirmed", "hitl_id": "HITL-1"})
            state["status"] = "archived"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            emit_event("archive", "archive", {"reason": "HITL-1 confirmed RED"})
            return state

    elif status == "awaiting-hitl-2":
        if decision == "dispute":
            state["hitl_decision"] = "disputed"
            emit_event("hitl_decision", "hitl-2", {"decision": "disputed", "hitl_id": "HITL-2"})
            state = run_financier(state)
            save_state(state)
            if state.get("finances", {}).get("verdict") == "DEAD":
                state = run_hitl_2(state)
                save_state(state)
                return state
            state = run_synthesizer(state)
            save_state(state)
            state = run_hitl_3(state)
            save_state(state)
            return state
        else:
            state["hitl_decision"] = "confirmed"
            emit_event("hitl_decision", "hitl-2", {"decision": "confirmed", "hitl_id": "HITL-2"})
            state["status"] = "archived"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            emit_event("archive", "archive", {"reason": "HITL-2 confirmed DEAD"})
            return state

    elif status == "awaiting-hitl-3":
        state["hitl_decision"] = decision
        emit_event("hitl_decision", "hitl-3", {"decision": decision, "hitl_id": "HITL-3"})
        if decision == "go":
            state["status"] = "succeeded"
        else:
            state["status"] = "archived"
            emit_event("archive", "archive", {"reason": "HITL-3 NO-GO"})
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return state

    return state


def run_post_arch_loop(state: dict[str, Any]) -> dict[str, Any]:
    for arch_pass in range(2):
        state = run_architect(state)
        save_state(state)
        if state.get("arch_iterations", 0) >= 2:
            state["status"] = "archived"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            emit_event("archive", "archive", {"reason": "max arch_iterations reached"})
            return state
        state = run_reviewer(state)
        save_state(state)
        review_verdict = state.get("reviewer_verdict", "YELLOW")
        if review_verdict == "GREEN":
            break
        if review_verdict == "RED":
            state = run_hitl_2(state)
            save_state(state)
            return state
        if review_verdict == "YELLOW" and arch_pass == 1:
            state["status"] = "archived"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            emit_event("archive", "archive", {"reason": "max arch_iterations reached after second YELLOW"})
            return state
    return state


def run_full(state: dict[str, Any]) -> dict[str, Any]:
    if CONTINUE_RUN_ID and HITL_DECISION:
        return continue_after_hitl(state)

    state = run_brainstormer(state)
    save_state(state)

    state = run_scout(state)
    save_state(state)

    state = run_reviewer(state)
    save_state(state)

    verdict = state.get("reviewer_verdict", "YELLOW")
    if verdict == "RED":
        state = run_hitl_1(state)
        save_state(state)
        return state
    if verdict == "YELLOW":
        state = run_post_arch_loop(state)
        if state.get("status") == "archived":
            return state

    state = run_strategist(state)
    save_state(state)

    strat_result = state.get("strategy", {})
    strat_verdict = strat_result.get("verdict", "FIT") if isinstance(strat_result, dict) else "FIT"
    if strat_verdict in ("NO-FIT",):
        state["status"] = "archived"
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        emit_event("archive", "archive", {"reason": f"STRAT verdict={strat_verdict}"})
        return state

    state = run_financier(state)
    save_state(state)

    if state.get("finances", {}).get("verdict") == "DEAD":
        state = run_hitl_2(state)
        save_state(state)
        return state

    state = run_synthesizer(state)
    save_state(state)
    state = run_hitl_3(state)
    save_state(state)
    return state


ROUTER["full"] = run_full


def get_step_status(state: dict[str, Any], step_name: str) -> str:
    if step_name == "reviewer":
        verdict = state.get("reviewer_verdict", "YELLOW")
        return f"verdict-{verdict.lower()}"
    if step_name == "architect":
        if state.get("arch_iterations", 0) >= 2:
            return "arch-max-iterations"
        return "arch-complete"
    if step_name == "strategist":
        strat = state.get("strategy", {})
        verdict = strat.get("verdict", "FIT") if isinstance(strat, dict) else "FIT"
        return f"verdict-{verdict.lower()}"
    if step_name == "financier":
        verdict = state.get("finances", {}).get("verdict", "VIABLE")
        return f"verdict-{verdict.lower()}"
    if step_name in ("hitl-1", "hitl-2", "hitl-3"):
        return f"awaiting-{step_name}"
    if step_name == "synthesizer":
        return "ready-for-hitl-3"
    return "ok"


def main():
    try:
        if STEP_NAME:
            state = load_state()
            if not state:
                if not TOPIC or not DOMAIN:
                    print("ERROR: TOPIC and DOMAIN must be set for first step", file=sys.stderr)
                    sys.exit(1)
                state = {
                    "topic": TOPIC,
                    "domain": DOMAIN,
                    "constraints": CONSTRAINTS,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "arch_iterations": 0,
                    "history": [],
                }
            runner = ROUTER.get(STEP_NAME)
            if not runner:
                raise RuntimeError(f"Unknown step: {STEP_NAME}")
            print(f"RUN_ID={RUN_ID} STEP={STEP_NAME}")
            state = runner(state)
            save_state(state)
            if QDRANT_ENABLED:
                try:
                    create_or_update_task(state)
                except Exception as exc:
                    print(f"QDRANT_TASK_UPDATE_ERROR err={exc}", file=sys.stderr)
            status = state.get("status", get_step_status(state, STEP_NAME))
            print(json.dumps({"step": STEP_NAME, "status": status}, ensure_ascii=False))
            gh_output = os.environ.get("GITHUB_OUTPUT")
            if gh_output:
                with open(gh_output, "a", encoding="utf-8") as f:
                    f.write(f"status={status}\n")
            return

        if CONTINUE_RUN_ID and HITL_DECISION:
            print(f"Continuing run {CONTINUE_RUN_ID} with decision={HITL_DECISION}")
            src = BASE_DIR / "artifacts" / "_continued"
            if not src.exists() or not (src / "state.json").exists():
                download_previous_artifacts(CONTINUE_RUN_ID)
            state = json.loads((src / "state.json").read_text(encoding="utf-8"))
            state["hitl_decision"] = HITL_DECISION
        else:
            if not TOPIC or not DOMAIN:
                print("ERROR: TOPIC and DOMAIN must be set", file=sys.stderr)
                sys.exit(1)
            state = {
                "topic": TOPIC,
                "domain": DOMAIN,
                "constraints": CONSTRAINTS,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "arch_iterations": 0,
                "history": [],
            }

        print(f"RUN_ID={RUN_ID}")
        print(f"TOPIC={state.get('topic')}")
        print(f"DOMAIN={state.get('domain')}")
        print(f"CONSTRAINTS={state.get('constraints')}")
        print(f"MODEL={MODEL}")
        sys.stdout.flush()

        if QDRANT_ENABLED:
            try:
                create_or_update_task(state)
            except Exception as exc:
                print(f"QDRANT_TASK_CREATE_ERROR err={exc}", file=sys.stderr)

        state = run_full(state)
        save_artifact("final", state)
        print("Pipeline complete. Final status:", state.get("status"))
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            save_artifact("final", {"status": "error", "error": str(exc)})
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
