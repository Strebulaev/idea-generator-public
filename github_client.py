import os
import requests
from typing import Any

GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PRIVATE_REPO_TOKEN = os.environ.get("PRIVATE_REPO_TOKEN", "")


def _request(method: str, path: str, repo: str | None = None, **kwargs: Any) -> Any:
    repo = repo or GITHUB_REPOSITORY
    token = PRIVATE_REPO_TOKEN if repo != GITHUB_REPOSITORY and PRIVATE_REPO_TOKEN else GITHUB_TOKEN
    if not token or not repo:
        return None
    url = f"https://api.github.com/repos/{repo}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Accept"] = "application/vnd.github+json"
    resp = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    resp.raise_for_status()
    if resp.status_code == 204:
        return None
    return resp.json()


def create_workflow_dispatch(workflow: str, ref: str, inputs: dict[str, Any]) -> dict[str, Any]:
    path = f"/actions/workflows/{workflow}/dispatches"
    payload = {"ref": ref, "inputs": inputs}
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return {"status": resp.status_code}


def get_issue(issue_number: int, repo: str | None = None) -> dict[str, Any] | None:
    path = f"/issues/{issue_number}"
    return _request("GET", path, repo=repo)


def get_issue_comments(issue_number: int, repo: str | None = None) -> list[dict[str, Any]]:
    path = f"/issues/{issue_number}/comments"
    result = _request("GET", path, repo=repo)
    if not result:
        return []
    return result


def list_issues(repo: str | None = None, state: str = "open", labels: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"state": state}
    if labels:
        params["labels"] = labels
    data = _request("GET", "/issues", repo=repo, params=params)
    if not data:
        return []
    return [issue for issue in data if "pull_request" not in issue]


def post_comment(issue_number: int, body: str, repo: str | None = None) -> dict[str, Any]:
    path = f"/issues/{issue_number}/comments"
    payload = {"body": body}
    result = _request("POST", path, repo=repo, json=payload)
    return result or {}


def add_labels(issue_number: int, labels: list[str], repo: str | None = None) -> dict[str, Any]:
    path = f"/issues/{issue_number}/labels"
    payload = {"labels": labels}
    result = _request("POST", path, repo=repo, json=payload)
    return result or {}
