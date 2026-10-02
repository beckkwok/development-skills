"""Thin, dependency-free wrapper around the GitHub CLI (``gh``).

Every network interaction in the review skills goes through here so behaviour is
consistent and failures produce actionable messages.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any


class GhError(RuntimeError):
    """Raised when ``gh`` is missing, unauthenticated, or a command fails."""


def _gh(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    exe = shutil.which("gh")
    if not exe:
        raise GhError(
            "GitHub CLI 'gh' not found on PATH. Install it from https://cli.github.com/ "
            "and run 'gh auth login'."
        )
    proc = subprocess.run(
        [exe, *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise GhError(
            f"gh {' '.join(args)} failed with exit code {proc.returncode}: "
            f"{proc.stderr.strip()}"
        )
    return proc


def check_auth() -> dict[str, Any]:
    """Verify ``gh`` is installed and authenticated."""
    proc = _gh(["auth", "status"], check=False)
    if proc.returncode != 0:
        raise GhError("gh is not authenticated. Run: gh auth login\n" + proc.stderr.strip())
    version = _gh(["version"], check=False).stdout.splitlines()
    return {"ok": True, "version": version[0] if version else "unknown"}


def normalize_repo(repo: str) -> str:
    """Accept ``owner/repo`` or a GitHub URL and return ``owner/repo``."""
    repo = repo.strip()
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?\s]+)", repo)
    if m:
        return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    if repo.count("/") == 1:
        return repo.removesuffix(".git")
    raise ValueError(f"Cannot parse repo spec {repo!r} (expected 'owner/repo' or a GitHub URL)")


def _api_jsonl(endpoint: str) -> list[dict[str, Any]]:
    """Call ``gh api --paginate`` and parse the JSONL stream into objects."""
    proc = _gh(["api", "--paginate", "--jq", ".[]", endpoint])
    out: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


_PR_FIELDS = ",".join(
    [
        "number",
        "title",
        "body",
        "url",
        "state",
        "isDraft",
        "author",
        "baseRefName",
        "headRefName",
        "headRefOid",
        "additions",
        "deletions",
        "changedFiles",
        "labels",
    ]
)

_ISSUE_FIELDS = ",".join(
    [
        "number",
        "title",
        "body",
        "url",
        "state",
        "author",
        "labels",
        "comments",
        "createdAt",
        "updatedAt",
    ]
)


def pr_files(repo: str, number: int) -> list[dict[str, Any]]:
    """Return changed files with ``filename``, ``status`` and ``patch`` (when present)."""
    repo = normalize_repo(repo)
    return _api_jsonl(f"repos/{repo}/pulls/{number}/files")


def pr_fetch(repo: str, number: int, *, include_diff: bool = True) -> dict[str, Any]:
    """Fetch PR metadata, changed files and (optionally) the unified diff."""
    repo = normalize_repo(repo)
    meta = json.loads(
        _gh(["pr", "view", str(number), "--repo", repo, "--json", _PR_FIELDS]).stdout
    )
    files = pr_files(repo, number)
    diff = _gh(["pr", "diff", str(number), "--repo", repo]).stdout if include_diff else ""
    return {"repo": repo, "number": number, "meta": meta, "files": files, "diff": diff}


def repo_default_branch(repo: str) -> str:
    """Return the repository's default branch name (falls back to ``main``)."""
    repo = normalize_repo(repo)
    proc = _gh(["repo", "view", repo, "--json", "defaultBranchRef"], check=False)
    if proc.returncode != 0:
        return "main"
    data = json.loads(proc.stdout or "{}")
    return (data.get("defaultBranchRef") or {}).get("name") or "main"


def branch_exists(repo: str, branch: str) -> bool:
    """Return True when a branch already exists on the remote."""
    repo = normalize_repo(repo)
    proc = _gh(["api", f"repos/{repo}/git/ref/heads/{branch}"], check=False)
    return proc.returncode == 0


def pr_create(
    repo: str,
    *,
    base: str,
    head: str,
    title: str,
    body: str,
    draft: bool = False,
    reviewers: list[str] | None = None,
    assignees: list[str] | None = None,
) -> str:
    """Create a pull request and return its URL."""
    repo = normalize_repo(repo)
    args = [
        "pr", "create", "--repo", repo, "--base", base, "--head", head,
        "--title", title, "--body-file", "-",
    ]
    if draft:
        args.append("--draft")
    for reviewer in reviewers or []:
        args += ["--reviewer", reviewer]
    for assignee in assignees or []:
        args += ["--assignee", assignee]
    proc = _gh(args, input_text=body)
    return proc.stdout.strip()


def issue_fetch(repo: str, number: int) -> dict[str, Any]:
    """Fetch an issue including its comments."""
    repo = normalize_repo(repo)
    return json.loads(
        _gh(["issue", "view", str(number), "--repo", repo, "--json", _ISSUE_FIELDS]).stdout
    )


def label_ensure(repo: str, names: list[str]) -> list[str]:
    """Create any missing labels (idempotent via ``--force``) and return their names."""
    repo = normalize_repo(repo)
    ensured: list[str] = []
    for name in names:
        if not name:
            continue
        _gh(["label", "create", name, "--repo", repo, "--force"])
        ensured.append(name)
    return ensured


def issue_edit(
    repo: str,
    number: int,
    *,
    add_assignees: list[str] | None = None,
    add_labels: list[str] | None = None,
) -> str:
    """Add assignees and/or labels to an issue and return its URL."""
    repo = normalize_repo(repo)
    assignees = [a for a in (add_assignees or []) if a]
    labels = [lbl for lbl in (add_labels or []) if lbl]
    if not assignees and not labels:
        raise ValueError("issue_edit requires at least one assignee or label")
    args = ["issue", "edit", str(number), "--repo", repo]
    for assignee in assignees:
        args += ["--add-assignee", assignee]
    for label in labels:
        args += ["--add-label", label]
    proc = _gh(args)
    return proc.stdout.strip()


def linked_prs(repo: str, issue: int) -> list[int]:
    """Return PR numbers cross-referenced from an issue timeline (oldest first)."""
    repo = normalize_repo(repo)
    proc = _gh(
        [
            "api", "--paginate", "--jq",
            ".[] | select(.event==\"cross-referenced\")"
            " | .source.issue | select(.pull_request != null) | .number",
            f"repos/{repo}/issues/{issue}/timeline",
        ],
        check=False,
    )
    if proc.returncode != 0:
        return []
    out: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.isdigit() and int(line) not in out:
            out.append(int(line))
    return out


def comment_post(repo: str, number: int, body: str, kind: str = "pr") -> str:
    """Post a new comment on a PR or issue and return its URL."""
    repo = normalize_repo(repo)
    verb = "pr" if kind == "pr" else "issue"
    proc = _gh(
        [verb, "comment", str(number), "--repo", repo, "--body-file", "-"],
        input_text=body,
    )
    return proc.stdout.strip()


def comment_update(repo: str, comment_id: int, body: str) -> str | None:
    """Edit an existing issue/PR comment in place and return its URL."""
    repo = normalize_repo(repo)
    payload = json.dumps({"body": body})
    proc = _gh(
        ["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{comment_id}", "--input", "-"],
        input_text=payload,
    )
    return json.loads(proc.stdout).get("html_url")


def find_comment(repo: str, number: int, marker: str) -> dict[str, Any] | None:
    """Find the first issue/PR comment whose body contains ``marker``."""
    repo = normalize_repo(repo)
    for comment in _api_jsonl(f"repos/{repo}/issues/{number}/comments"):
        if marker in (comment.get("body") or ""):
            return comment
    return None


def fetch_raw_file(repo: str, path: str, ref: str | None = None) -> str | None:
    """Fetch a single file's raw contents, or ``None`` when it does not exist."""
    repo = normalize_repo(repo)
    args = ["api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}"]
    if ref:
        args += ["-f", f"ref={ref}"]
    proc = _gh(args, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout
