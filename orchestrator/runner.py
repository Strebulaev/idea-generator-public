import os
import sys
import json
import time
import traceback
import yaml
import requests
import base64
from pathlib import Path
from datetime import datetime
from typing import Any

RUN_ID = os.environ.get("RUN_ID", f"local-{int(time.time())}")
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

BASE_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
ARTIFACTS_DIR = BASE_DIR / "artifacts" / RUN_ID
TEMPLATES_DIR = BASE_DIR / "templates"

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


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


def call_kilo(system_prompt: str, user_prompt: str, response_schema: dict | None = None) -> dict:
    if not KILO_API_KEY:
        print("WARNING: KILO_API_KEY is not set. Returning mock response.", file=sys.stderr)
        return {"mock": True, "system": system_prompt[:100], "user": user_prompt[:100]}

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

    resp = requests.post(
        f"{KILO_URL}/chat/completions",
        headers={"Authorization": f"Bearer {KILO_API_KEY}"},
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw": content}


def save_artifact(name: str, data: dict | str) -> Path:
    path = ARTIFACTS_DIR / f"{name}.json"
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_artifact(name: str) -> Any:
    path = ARTIFACTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def step(name: str, agent_id: str, context: dict[str, Any]) -> dict:
    print(f"[STEP] {name} -> agent={agent_id}")
    agent = load_agent(agent_id)
    system_prompt = render_prompt(agent["system_prompt"], context)
    user_prompt = json.dumps(context, ensure_ascii=False)
    result = call_kilo(system_prompt, user_prompt, agent.get("output_schema"))
    save_artifact(name, result)
    return result


def emit_hitl_issue(hitl_id: str, state: dict[str, Any], prompt_text: str, options: list[str]) -> dict:
    issue_title = f"[HITL] {hitl_id} — требуется решение для RUN_ID={RUN_ID}"
    body = json.dumps(
        {
            "run_id": RUN_ID,
            "hitl_id": hitl_id,
            "prompt": prompt_text,
            "options": options,
            "state_preview": {k: state[k] for k in ["topic", "domain", "constraints", "reviewer_verdict"] if k in state},
        },
        ensure_ascii=False,
        indent=2,
    )
    issue = create_github_issue(issue_title, body, labels=["idea-generator", "hitl", "awaiting-decision"])
    print(f"HITL issue created: {issue.get('html_url') if issue else 'N/A'}")
    return issue or {}


def save_state(state: dict[str, Any], status: str, reason: str = "") -> None:
    state["status"] = status
    if reason:
        state["archive_reason"] = reason
    save_artifact("final", state)


def run():
    state_path = ARTIFACTS_DIR / "final.json"
    continued = False

    try:
        if CONTINUE_RUN_ID and HITL_DECISION:
            print(f"Continuing run {CONTINUE_RUN_ID} with decision={HITL_DECISION}")
            src = BASE_DIR / "artifacts" / "_continued"
            if not src.exists() or not (src / "final.json").exists():
                download_previous_artifacts(CONTINUE_RUN_ID)
            state = json.loads((src / "final.json").read_text(encoding="utf-8"))
            state["hitl_decision"] = HITL_DECISION
            continued = True
        else:
            if not TOPIC or not DOMAIN:
                print("ERROR: TOPIC and DOMAIN must be set", file=sys.stderr)
                save_state({"topic": TOPIC, "domain": DOMAIN, "constraints": CONSTRAINTS}, "error", "missing_inputs")
                sys.exit(1)

            state = {
                "topic": TOPIC,
                "domain": DOMAIN,
                "constraints": CONSTRAINTS,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "arch_iterations": 0,
                "history": [],
            }

        print(f"RUN_ID={RUN_ID}")
        print(f"TOPIC={state.get('topic')}")
        print(f"DOMAIN={state.get('domain')}")
        print(f"CONSTRAINTS={state.get('constraints')}")
        print(f"MODEL={MODEL}")
        print(f"CONTINUED={continued}")

        if not continued:
            # 1. Brainstormer
            bs_result = step("01_brainstormer", "brainstormer", state)
            state["ideas"] = bs_result.get("ideas", [])
            if not state["ideas"]:
                print("ERROR: Brainstormer returned no ideas", file=sys.stderr)
                save_state(state, "error", "no_ideas")
                sys.exit(1)

            current_idea = state["ideas"][0]
            state["current_idea"] = current_idea

            # 2. Scout
            scout_result = step("02_scout", "scout", state)
            state["scout_data"] = scout_result.get("research", [])

            # 3. Reviewer
            reviewer_result = step("03_reviewer", "reviewer", state)
            verdicts = reviewer_result.get("verdicts", [])
            current_verdict = verdicts[0]["verdict"] if verdicts else "YELLOW"
            state["reviewer_verdict"] = current_verdict
            state["reviewer_reasoning"] = verdicts[0].get("reasoning", "") if verdicts else ""
            state["risks"] = verdicts[0].get("risks", []) if verdicts else []

            if current_verdict == "RED":
                hitl_result = step("hitl-2", "hitl-2", state)
                emit_hitl_issue(
                    "HITL-2",
                    state,
                    hitl_result.get("hitl_prompt", "Reviewer вынес RED. Подтвердить?"),
                    hitl_result.get("options", ["Подтверждаю RED", "Оспариваю"]),
                )
                save_state(state, "awaiting-hitl-2", "hitl_2_red")
                print("Stopped at HITL-2. Create issue and re-run with hitl_decision.")
                return

        else:
            current_idea = state.get("current_idea", state.get("ideas", [{}])[0])
            current_verdict = state.get("reviewer_verdict", "YELLOW")
            if HITL_DECISION == "disputed" and state.get("status") == "awaiting-hitl-2":
                current_verdict = "YELLOW"

        if current_verdict == "GREEN":
            pass
        elif current_verdict == "YELLOW" or (continued and HITL_DECISION == "disputed"):
            state["arch_iterations"] = state.get("arch_iterations", 0)
            arch_result = step("04_architect", "architect", state)
            state["mutated_idea"] = arch_result.get("mutated_idea", current_idea)
            state["arch_iterations"] = arch_result.get("arch_iterations", state.get("arch_iterations", 0) + 1)
            current_idea = state["mutated_idea"]
            state["current_idea"] = current_idea
        else:
            save_state(state, "archived", "red_confirmed")
            print("Archived due to RED verdict.")
            return

        # 4. Strategist
        strat_result = step("05_strategist", "strategist", state)
        state["strategy"] = strat_result

        # 5. Financier
        fin_result = step("06_financier", "financier", state)
        state["finances"] = fin_result

        fin_verdict = fin_result.get("verdict", "TIGHT")
        if fin_verdict == "DEAD":
            hitl_result = step("hitl-4", "hitl-4", state)
            emit_hitl_issue(
                "HITL-4",
                state,
                hitl_result.get("hitl_prompt", "Финансы показали DEAD. Подтвердить?"),
                hitl_result.get("options", ["Подтверждаю DEAD", "Оспариваю"]),
            )
            save_state(state, "awaiting-hitl-4", "hitl_4_dead")
            print("Stopped at HITL-4. Create issue and re-run with hitl_decision.")
            return

        if continued and HITL_DECISION == "disputed" and state.get("status") == "awaiting-hitl-4":
            pass

        # 6. Synthesizer
        synth_result = step("07_synthesizer", "synthesizer", state)
        state["synthesis"] = synth_result

        # 7. HITL-5
        hitl_result = step("hitl-5", "hitl-5", state)
        emit_hitl_issue(
            "HITL-5",
            state,
            hitl_result.get("hitl_prompt", "Финальное решение: GO или NO-GO?"),
            hitl_result.get("options", ["GO", "NO-GO"]),
        )
        save_state(state, "awaiting-hitl-5", "hitl_5_final")
        print("Stopped at HITL-5. Create issue and re-run with hitl_decision.")
        return

    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            save_state(state if 'state' in dir() else {}, "error", str(exc))
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    run()
