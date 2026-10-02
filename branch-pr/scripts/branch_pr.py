#!/usr/bin/env python3
"""Create a branch from a base branch, push it, and open a pull request.

Write-capable, with guardrails:

- never commits file changes (the branch starts empty at the base HEAD);
- never force-pushes;
- refuses to overwrite an existing local or remote branch;
- refuses to run on a dirty working tree (unless ``--allow-dirty``);
- ``--dry-run`` prints the plan without touching the remote.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "_review-lib"))

from reviewlib import gh  # noqa: E402

LABEL_TO_TYPE = {
    "bug": "fix",
    "bugfix": "fix",
    "fix": "fix",
    "enhancement": "feature",
    "feature": "feature",
    "documentation": "docs",
    "docs": "docs",
    "chore": "chore",
    "refactor": "refactor",
    "maintenance": "chore",
}

TITLE_PREFIX_TO_TYPE = {
    "feat": "feature",
    "feature": "feature",
    "fix": "fix",
    "bugfix": "fix",
    "docs": "docs",
    "doc": "docs",
    "chore": "chore",
    "refactor": "refactor",
    "test": "test",
    "perf": "perf",
}


class SkillError(RuntimeError):
    pass


def slugify(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0].strip("-")
    return slug or "task"


def resolve_type(labels: list[str], title: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    for label in labels:
        if label.lower() in LABEL_TO_TYPE:
            return LABEL_TO_TYPE[label.lower()]
    match = re.match(r"^([a-zA-Z]+)[\(:]", (title or "").strip())
    if match and match.group(1).lower() in TITLE_PREFIX_TO_TYPE:
        return TITLE_PREFIX_TO_TYPE[match.group(1).lower()]
    return ""


def run(cmd: list[str], cwd: str | None = None, *, check: bool = True) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise SkillError(f"{' '.join(cmd)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout.strip()


def git(repo_root: str, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=repo_root, check=check)


def ensure_repo_root(args: argparse.Namespace, repo: str) -> str:
    if args.repo_root:
        root = Path(args.repo_root).expanduser()
        if not (root / ".git").exists():
            raise SkillError(f"--repo-root is not a git checkout: {root}")
        return str(root)
    if args.clone_dir:
        root = Path(args.clone_dir).expanduser()
        if not (root / ".git").exists():
            root.parent.mkdir(parents=True, exist_ok=True)
            run(["gh", "repo", "clone", repo, str(root), "--", "--quiet"])
        return str(root)
    raise SkillError("Provide --repo-root (existing checkout) or --clone-dir (clone target).")


def split_values(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def build_pr_body(issue: dict[str, Any] | None, title: str) -> str:
    if issue:
        body = issue.get("body") or ""
        return (
            f"## Summary\n\n{issue.get('title', title)}\n\n"
            f"## Context\n\n{body.strip() or '_(no issue description)_'}\n\n"
            f"Closes #{issue.get('number')}\n"
        )
    return f"## Summary\n\n{title}\n"


def execute(args: argparse.Namespace) -> dict[str, Any]:
    repo = gh.normalize_repo(args.repo)
    notes: list[str] = []

    issue = gh.issue_fetch(repo, args.issue) if args.issue else None

    # --- base branch -------------------------------------------------------
    base = args.base or "main"
    if not gh.branch_exists(repo, base):
        if args.base:
            raise SkillError(f"base branch '{base}' does not exist in {repo}")
        fallback = gh.repo_default_branch(repo)
        notes.append(f"base '{base}' not found; using default branch '{fallback}'")
        base = fallback

    # --- branch name -------------------------------------------------------
    labels = [lbl.get("name", "") for lbl in (issue or {}).get("labels", []) if isinstance(lbl, dict)]
    issue_title = (issue or {}).get("title", "")
    title = args.title or issue_title or ""
    branch_type = resolve_type(labels, title or args.branch or "", args.type) or ("feature" if issue else "chore")
    slug = slugify(title or args.branch or "task")

    if args.branch:
        branch = args.branch
    elif issue:
        branch = f"{branch_type}/{issue['number']}-{slug}"
    elif title:
        branch = f"{branch_type}/{slug}"
    else:
        raise SkillError("Provide --issue, --title, or --branch to name the branch.")

    pr_title = title or branch
    body = Path(args.body_file).read_text(encoding="utf-8-sig") if args.body_file else build_pr_body(issue, pr_title)
    reviewers = split_values(args.reviewer)
    assignees = split_values(args.assignee)

    plan = {
        "repo": repo,
        "base": base,
        "branch": branch,
        "title": pr_title,
        "draft": bool(args.draft),
        "reviewers": reviewers,
        "assignees": assignees,
        "notes": notes,
    }

    if gh.branch_exists(repo, branch):
        raise SkillError(f"branch '{branch}' already exists on {repo}; refusing to overwrite")

    if args.dry_run:
        plan["dry_run"] = True
        plan["steps"] = [
            f"git fetch origin {base}",
            f"git checkout -b {branch} origin/{base}",
            f"git push -u origin {branch}",
            f"gh pr create --base {base} --head {branch} --title {pr_title!r}",
        ]
        return plan

    repo_root = ensure_repo_root(args, repo)

    if git(repo_root, "status", "--porcelain") and not args.allow_dirty:
        raise SkillError("working tree is dirty; commit/stash first or pass --allow-dirty")

    git(repo_root, "fetch", "origin", base)
    git(repo_root, "checkout", "-b", branch, f"origin/{base}")
    git(repo_root, "push", "-u", "origin", branch)

    pr_url = gh.pr_create(
        repo, base=base, head=branch, title=pr_title, body=body,
        draft=args.draft, reviewers=reviewers, assignees=assignees,
    )
    plan["pr_url"] = pr_url
    plan["dry_run"] = False
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a branch and open a PR")
    parser.add_argument("--repo", required=True, help="owner/repo or GitHub URL")
    parser.add_argument("--base", help="base branch (default: main, else the repo default)")
    parser.add_argument("--issue", type=int, help="issue number to derive name/PR from")
    parser.add_argument("--branch", help="explicit branch name (overrides derivation)")
    parser.add_argument("--type", help="branch type prefix (feature/fix/docs/chore/...)")
    parser.add_argument("--title", help="PR title (default: issue title)")
    parser.add_argument("--body-file", help="file with the PR body")
    parser.add_argument("--reviewer", action="append", help="reviewer login (repeatable or comma-separated)")
    parser.add_argument("--assignee", action="append", help="assignee login (repeatable or comma-separated)")
    parser.add_argument("--draft", action="store_true", help="open the PR as a draft")
    parser.add_argument("--repo-root", help="existing local checkout")
    parser.add_argument("--clone-dir", help="directory to clone into if no checkout exists")
    parser.add_argument("--allow-dirty", action="store_true", help="allow a dirty working tree")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    try:
        result = execute(args)
    except (SkillError, gh.GhError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"branch: {result['branch']} (from {result['base']})")
        if result.get("pr_url"):
            print(f"pr: {result['pr_url']}")
        elif result.get("dry_run"):
            print("dry-run: no changes made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
