import base64, requests

GITHUB_API = "https://api.github.com"

def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

def create_branch(repo: str, base_branch: str, new_branch: str, token: str) -> str:
    # fetch base SHA and create new ref…

def commit_file(repo: str, branch: str, path: str, content_bytes: bytes, message: str, token: str) -> None:
    # use the contents API to put/update the file…

def open_pr(repo: str, branch: str, base: str, title: str, body: str, token: str) -> str:
    # open a pull request and return its URL…
