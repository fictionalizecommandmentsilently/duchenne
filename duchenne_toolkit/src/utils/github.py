from __future__ import annotations

import base64
from typing import Optional, Tuple

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def _split_repo(repo: str) -> Tuple[str, str]:
    if "/" not in repo:
        raise ValueError('repo must be "owner/name"')
    owner, name = repo.split("/", 1)
    return owner, name


def create_branch(repo: str, base_branch: str, new_branch: str, token: str) -> str:
    """Create a branch off base_branch. Returns 'refs/heads/<new_branch>'."""
    owner, name = _split_repo(repo)

    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{name}/git/ref/heads/{base_branch}",
        headers=_headers(token),
    )
    if r.status_code == 404:
        raise RuntimeError(f"Base branch '{base_branch}' not found")
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]

    ref = f"refs/heads/{new_branch}"
    r2 = requests.post(
        f"{GITHUB_API}/repos/{owner}/{name}/git/refs",
        headers=_headers(token),
        json={"ref": ref, "sha": base_sha},
    )
    # 422 = already exists
    if r2.status_code == 422:
        return ref
    r2.raise_for_status()
    return ref


def _get_file_sha(repo: str, path: str, branch: str, token: str) -> Optional[str]:
    owner, name = _split_repo(repo)
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{name}/contents/{path}",
        headers=_headers(token),
        params={"ref": branch},
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("sha")


def commit_file(
    repo: str,
    branch: str,
    path: str,
    content_bytes: bytes,
    message: str,
    token: str,
) -> None:
    """Create or update a file on a branch using the Contents API."""
    owner, name = _split_repo(repo)
    sha = _get_file_sha(repo, path, branch, token)

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(
        f"{GITHUB_API}/repos/{owner}/{name}/contents/{path}",
        headers=_headers(token),
        json=payload,
    )
    r.raise_for_status()


def open_pr(repo: str, branch: str, base: str, title: str, body: str, token: str) -> str:
    """Open a pull request and return its HTML URL."""
    owner, name = _split_repo(repo)
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{name}/pulls",
        headers=_headers(token),
        json={"title": title, "head": branch, "base": base, "body": body},
    )
    r.raise_for_status()
    return r.json()["html_url"]
