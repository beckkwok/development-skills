#!/usr/bin/env python3
"""QA verification for a GitHub issue.

Independent skill: given only a repo and an issue, resolve what was built,
run the tests, and render a QA report. No coding-session state is required,
so this can run on a different machine or model than the coding agent.

Subcommands:

- ``resolve`` - extract acceptance criteria, find the linked PR/branch, and
  suggest test commands.
- ``run`` - execute one verification step and append uniform evidence
  (command, exit code, output) to a results file.
- ``render`` - build the QA report comment from the results file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "_review-lib"))

from reviewlib import config as config_mod, gh  # noqa: E402

COMMENT_MARKER = "<!-- qa-verify-agent -->"


class SkillError(RuntimeError):
    pass

TASK_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")
AC_HEADINGS = [
    "acceptance criteria",
    "definition of done",
    "acceptance",
    "expected behavior",
    "expected result",
    "expected",
    "requirements",
]
BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*(.+?)\s*$")

STACK_TESTS = [
    ("pubspec.yaml", "flutter test"),
    ("package.json", "npm test"),
    ("go.mod", "go test ./..."),
    ("Cargo.toml", "cargo test"),
    ("pom.xml", "mvn -q test"),
    ("build.gradle", "./gradlew test"),
    ("pytest.ini", "pytest"),
    ("setup.py", "pytest"),
    ("pyproject.toml", "pytest"),
    ("Gemfile", "bundle exec rake test"),
]

MAX_OUTPUT_CHARS = 6000


def _read_json(path: str | None) -> dict[str, Any]:
    if path in (None, "-"):
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def extract_criteria(body: str) -> list[dict[str, Any]]:
    """Acceptance criteria: task-list items first, acceptance sections as fallback."""
    body = body or ""
    criteria: list[dict[str, Any]] = []
    for line in body.splitlines():
        match = TASK_RE.match(line)
        if match:
            criteria.append({"text": match.group(2), "source": "checklist"})
    if criteria:
        return [{"id": f"C{i + 1}", **item} for i, item in enumerate(criteria)]

    current: str | None = None
    sections: dict[str, list[str]] = {}
    for line in body.splitlines():
        stripped = line.strip().strip("*#").rstrip(":").strip().lower()
        if stripped in AC_HEADINGS:
            current = stripped
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    for lines in sections.values():
        for line in lines:
            match = BULLET_RE.match(line)
            if match and match.group(1):
                criteria.append({"text": match.group(1), "source": "acceptance-section"})
    return [{"id": f"C{i + 1}", **item} for i, item in enumerate(criteria)]


def detect_stack_commands(repo_root: str | None) -> list[str]:
    if not repo_root:
        return []
    root = Path(repo_root)
    if not root.is_dir():
        return []
    for marker, command in STACK_TESTS:
        if (root / marker).is_file() or (root / "app" / marker).is_file():
            return [command]
    return []


def cmd_resolve(args: argparse.Namespace) -> None:
    if args.issue_json:
        issue = _read_json(args.issue_json)
        repo = issue.get("_repo") or args.repo
    else:
        repo = gh.normalize_repo(args.repo)
        issue = gh.issue_fetch(repo, args.issue)
        issue["_repo"] = repo
    if not repo:
        raise SkillError("--repo is required when --issue-json has no _repo field")

    criteria = extract_criteria(issue.get("body") or "")

    pr_number = args.pr
    if pr_number is None and issue.get("number"):
        linked = gh.linked_prs(repo, issue["number"])
        pr_number = linked[-1] if linked else None

    target: dict[str, Any] = {"pr": pr_number, "branch": args.branch, "ref": args.ref}
    if pr_number is not None and target["ref"] is None:
        try:
            meta = gh.pr_fetch(repo, pr_number, include_diff=False)["meta"]
            target["branch"] = target["branch"] or meta.get("headRefName")
            target["ref"] = meta.get("headRefOid")
            target["url"] = meta.get("url")
        except gh.GhError as exc:
            target["error"] = str(exc)

    cfg = config_mod.resolve(repo_root=args.repo_root, repo=repo)
    configured = (cfg.get("commands") or {}).get("test")
    test_commands = [configured] if configured else detect_stack_commands(args.repo_root)

    json.dump(
        {
            "repo": repo,
            "issue": issue.get("number"),
            "issue_url": issue.get("url"),
            "issue_title": issue.get("title"),
            "criteria": criteria,
            "target": target,
            "test_commands": test_commands,
        },
        sys.stdout, indent=2, ensure_ascii=False,
    )
    sys.stdout.write("\n")


def cmd_run(args: argparse.Namespace) -> None:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args.command, shell=True, cwd=args.repo_root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=args.timeout,
        )
        exit_code: int | str = proc.returncode
        output = (proc.stdout + "\n" + proc.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        exit_code = "timeout"
        output = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
    duration = round(time.monotonic() - started, 1)

    truncated = len(output) > MAX_OUTPUT_CHARS
    record = {
        "step": args.step or args.command,
        "command": args.command,
        "exit_code": exit_code,
        "duration_s": duration,
        "output": output[:MAX_OUTPUT_CHARS],
        "truncated": truncated,
    }

    results: dict[str, Any] = {"steps": []}
    if args.out and Path(args.out).is_file():
        try:
            results = json.loads(Path(args.out).read_text(encoding="utf-8-sig"))
            results.setdefault("steps", [])
        except (json.JSONDecodeError, OSError):
            results = {"steps": []}
    results["steps"].append(record)
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    json.dump(record, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _criterion_line(criterion: dict[str, Any]) -> str:
    verdict = str(criterion.get("verdict", "unverified")).lower()
    box = "[x]" if verdict == "verified" else "[ ]"
    line = f"- {box} **{criterion.get('id', '')}** {criterion.get('text', '')}".rstrip()
    if criterion.get("support"):
        line += f" - _{criterion['support']}_"
    if verdict == "failed" and criterion.get("reason"):
        line += f" - FAILED: {criterion['reason']}"
    return line


def compute_verdict(results: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    steps = results.get("steps", [])
    criteria = results.get("criteria", [])
    if any(str(c.get("verdict", "")).lower() == "failed" for c in criteria):
        return "fail"
    if any(s.get("exit_code") != 0 for s in steps):
        return "fail"
    if not steps and not criteria:
        return "inconclusive"
    if any(str(c.get("verdict", "")).lower() != "verified" for c in criteria):
        return "inconclusive"
    return "pass"


def cmd_render(args: argparse.Namespace) -> None:
    if args.issue_json:
        issue = _read_json(args.issue_json)
    else:
        repo = gh.normalize_repo(args.repo)
        issue = gh.issue_fetch(repo, args.issue)
    results = _read_json(args.results) if args.results else {"steps": []}

    verdict = compute_verdict(results, args.verdict)
    label = {"pass": "QA PASS", "fail": "QA FAIL"}.get(verdict, "QA INCONCLUSIVE")

    lines = [f"## QA Report: {issue.get('title', 'issue')}", ""]
    lines += [f"- **Issue:** {issue.get('url', '')}"]
    target = results.get("target") or {}
    if target.get("pr"):
        lines += [f"- **Target:** PR #{target['pr']} ({target.get('branch', '?')}) @ `{str(target.get('ref', '?'))[:12]}`"]
    elif target.get("ref"):
        lines += [f"- **Target:** `{target['ref']}`"]
    if results.get("environment"):
        env = results["environment"]
        lines += [f"- **Environment:** {env if isinstance(env, str) else json.dumps(env)}"]
    lines += [f"- **Verdict:** **{label}**", ""]

    if results.get("summary"):
        lines += [str(results["summary"]).strip(), ""]
    if results.get("criteria"):
        lines += ["### Acceptance criteria", ""]
        lines += [_criterion_line(c) for c in results["criteria"]]
        lines += [""]
    if results.get("screenshots"):
        lines += ["### Screenshots", ""]
        for shot in results["screenshots"]:
            caption = shot.get("caption", "screenshot")
            if shot.get("url"):
                lines += [f"![{caption}]({shot['url']})", ""]
            else:
                lines += [f"- {caption} — `{shot.get('path', 'unknown path')}` _(attach manually)_", ""]
    if results.get("steps"):
        lines += ["### Proof (step by step)", ""]
        for i, step in enumerate(results["steps"], 1):
            lines += [f"#### {i}. {step.get('step', 'step')}", "", "```bash",
                      str(step.get("command", "")).strip(), "```",
                      f"exit code: `{step.get('exit_code')}` ({step.get('duration_s', '?')}s)", ""]
            if step.get("output"):
                lines += ["```", str(step["output"]).strip(), "```", ""]
            if step.get("truncated"):
                lines += ["_(output truncated)_", ""]
    else:
        lines += ["_No verification steps were recorded._", ""]

    applied = [g for g in (args.guidelines or "").split(",") if g]
    if applied:
        lines += ["Guidelines applied: " + ", ".join(f"`{g}`" for g in applied), ""]
    lines += [COMMENT_MARKER]
    body = "\n".join(lines).rstrip() + "\n"

    if args.comment_out:
        Path(args.comment_out).write_text(body, encoding="utf-8")
    sys.stdout.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QA verification for a GitHub issue")
    sub = parser.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("resolve", help="extract criteria and resolve the test target")
    p.add_argument("--repo", help="owner/repo (or _repo inside --issue-json)")
    p.add_argument("--issue", type=int, help="issue number (skipped with --issue-json)")
    p.add_argument("--issue-json", help="issue-fetch output file (offline mode)")
    p.add_argument("--pr", type=int, help="explicit PR to test")
    p.add_argument("--branch", help="explicit branch to test")
    p.add_argument("--ref", help="explicit commit sha to test")
    p.add_argument("--repo-root", help="local checkout for config/stack detection")
    p.set_defaults(func=lambda a: cmd_resolve(a))

    p = sub.add_parser("run", help="execute one verification step and record evidence")
    p.add_argument("--repo-root", required=True, help="checkout to run the command in")
    p.add_argument("--step", help="display name for this step")
    p.add_argument("--timeout", type=int, default=900, help="seconds before giving up")
    p.add_argument("--out", help="results file to append the step to")
    p.add_argument("command", help="shell command to run")
    p.set_defaults(func=lambda a: cmd_run(a))

    p = sub.add_parser("render", help="render the QA report comment")
    p.add_argument("--issue-json", help="issue-fetch output file")
    p.add_argument("--repo", help="owner/repo (used with --issue)")
    p.add_argument("--issue", type=int, help="issue number (used with --repo)")
    p.add_argument("--results", help="results JSON file")
    p.add_argument("--comment-out", help="write the report to this file")
    p.add_argument("--guidelines", help="comma-separated list of applied guidelines")
    p.add_argument("--verdict", choices=["pass", "fail", "inconclusive"],
                   help="override the computed verdict")
    p.set_defaults(func=lambda a: cmd_render(a))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (SkillError, gh.GhError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
