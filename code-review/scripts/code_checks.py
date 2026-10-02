#!/usr/bin/env python3
"""Static code-change analysis for a pull request.

Reads the JSON produced by ``_review-lib/cli.py pr-fetch``, scans added lines in
source files for common problems, checks whether tests accompany code changes,
and optionally runs the repo's configured lint/test commands.

Read-only on source: it never edits code. It may run tests only when
``--run-commands`` is passed and a local checkout is available.
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

from reviewlib import classify, config as config_mod, render  # noqa: E402

COMMENT_MARKER = "<!-- code-review-agent -->"

BLOCKER = "blocker"
ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITY_RANK = {BLOCKER: 0, ERROR: 1, WARNING: 2, INFO: 3}


def finding(severity: str, rule: str, message: str, file: str | None = None,
            line: int | None = None, detail: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if file:
        item["file"] = file
    if line:
        item["line"] = line
    if detail:
        item["detail"] = detail
    return item


# --------------------------------------------------------------------------- #
# Diff parsing (same convention as db_checks)
# --------------------------------------------------------------------------- #

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def iter_added_lines(patch: str):
    new_line: int | None = None
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            match = _HUNK_RE.match(raw)
            new_line = int(match.group(1)) if match else None
            continue
        if new_line is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            yield new_line, raw[1:]
            new_line += 1
        elif raw.startswith("-"):
            continue
        elif raw.startswith(" "):
            new_line += 1


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #

CONFLICT_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?:\s|$)")
TODO_RE = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")
EVAL_RE = re.compile(r"\b(?:eval|exec)\s*\(")
BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:")
PY_SWALLOW_RE = re.compile(r"except\s*(?:Exception\s*)?:\s*(?:pass|\.\.\.)\s*$")
JS_EMPTY_CATCH_RE = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}|\.catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)")

HIGH_SIGNAL_DEBUG = {
    ".js": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".jsx": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".ts": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".tsx": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".mjs": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".cjs": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".vue": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".svelte": re.compile(r"\bconsole\.(?:log|debug)\s*\(|\bdebugger\b"),
    ".rb": re.compile(r"\bbinding\.pry\b|\bbyebug\b"),
    ".py": re.compile(r"\bbreakpoint\s*\(|\bpdb\.set_trace\s*\(|\bimport\s+pdb\b"),
    ".php": re.compile(r"\bvar_dump\s*\(|\bdd\s*\(|\bprint_r\s*\("),
}

LOW_SIGNAL_DEBUG = {
    ".py": re.compile(r"\bprint\s*\("),
    ".rb": re.compile(r"\bputs\b"),
    ".go": re.compile(r"\bfmt\.Print(?:ln|f)?\s*\("),
    ".java": re.compile(r"\bSystem\.out\.print"),
    ".kt": re.compile(r"\bprintln\s*\("),
    ".rs": re.compile(r"\bdbg!\s*\(|\bprintln!\s*\("),
    ".cs": re.compile(r"\bConsole\.WriteLine\s*\("),
    ".dart": re.compile(r"\bprint\s*\("),
    ".swift": re.compile(r"\bprint\s*\("),
    ".c": re.compile(r"\bprintf\s*\("),
    ".cc": re.compile(r"\bprintf\s*\("),
    ".cpp": re.compile(r"\bprintf\s*\("),
}

SECRET_RES = [
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), BLOCKER, "private-key",
     "Private key material committed to the repository."),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), BLOCKER, "aws-access-key", "Possible AWS access key ID."),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), BLOCKER, "github-token", "Possible GitHub personal access token."),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), BLOCKER, "api-key", "Possible API secret key."),
    (re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b"
        r"\s*[:=]\s*['\"]([^'\"]{4,})['\"]"
    ), BLOCKER, "hardcoded-credential", "Hardcoded credential or secret."),
]

PLACEHOLDERS = ("changeme", "change_me", "example", "placeholder", "your_", "xxxx", "dummy",
                "sample", "test", "fake", "todo", "redacted", "****")


def _looks_placeholder(value: str) -> bool:
    low = value.lower()
    return any(marker in low for marker in PLACEHOLDERS)


def scan_added_line(path: str, line_no: int, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    ext = Path(path).suffix.lower()

    if CONFLICT_RE.search(text.strip()):
        findings.append(finding(BLOCKER, "merge-conflict", "Unresolved merge conflict marker.", path, line_no))

    for regex, severity, rule, message in SECRET_RES:
        match = regex.search(text)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            if _looks_placeholder(value):
                continue
            findings.append(finding(severity, rule, message, path, line_no))
            break

    if TODO_RE.search(text):
        findings.append(finding(WARNING, "todo", "Unresolved TODO/FIXME/HACK marker.", path, line_no))

    if EVAL_RE.search(text):
        findings.append(finding(WARNING, "eval-exec", "Use of eval/exec is a code-injection risk.", path, line_no))

    if PY_SWALLOW_RE.search(text.strip()):
        findings.append(finding(ERROR, "swallowed-exception", "Exception is silently swallowed.", path, line_no))
    elif BARE_EXCEPT_RE.search(text):
        findings.append(finding(ERROR, "bare-except",
                                "Bare 'except:' catches every exception, including system exits.", path, line_no))

    if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".vue", ".svelte") and JS_EMPTY_CATCH_RE.search(text):
        findings.append(finding(ERROR, "swallowed-exception", "Empty catch block swallows errors.", path, line_no))

    high = HIGH_SIGNAL_DEBUG.get(ext)
    if high and high.search(text):
        findings.append(finding(WARNING, "debug-statement", "Debugging statement left in the code.", path, line_no))
    else:
        low = LOW_SIGNAL_DEBUG.get(ext)
        if low and low.search(text):
            findings.append(finding(INFO, "debug-statement", "Print/debug output left in the code.", path, line_no))

    return findings


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #

def _test_requirement_finding(cfg: dict[str, Any], code_files: list[Any], test_files: list[Any]) -> dict[str, Any] | None:
    if not cfg.get("require_tests", True):
        return None
    if not code_files or test_files:
        return None
    return finding(
        ERROR, "missing-tests",
        "Source files changed but no tests were added or updated.",
        detail="Add or update tests covering the change (or set require_tests=false in .review/config.json).",
    )


def _run_command(label: str, command: str, repo_root: str) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            command, shell=True, cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
    except subprocess.TimeoutExpired:
        return finding(ERROR, f"{label}-timeout", f"Configured {label} command timed out.")
    if proc.returncode == 0:
        return None
    output = (proc.stdout + "\n" + proc.stderr).strip()
    tail = "\n".join(output.splitlines()[-15:])
    return finding(ERROR, f"{label}-failed", f"Configured {label} command failed (exit {proc.returncode}).",
                   detail=tail)


def analyze(pr: dict[str, Any], cfg: dict[str, Any], *, repo_root: str | None = None,
            run_commands: bool = False) -> dict[str, Any]:
    repo = pr.get("repo", "")
    files = pr.get("files", [])
    grouped = classify.classify_files(files, cfg)
    code_files = grouped["code"]
    test_files = grouped["test"]
    other_files = grouped["other"]

    findings: list[dict[str, Any]] = []
    for entry in code_files:
        path = classify.path_of(entry)
        patch = entry.get("patch") if isinstance(entry, dict) else None
        if not patch:
            findings.append(finding(INFO, "no-patch",
                                    "File changed but no patch was returned (binary or too large).", path))
            continue
        for line_no, text in iter_added_lines(patch):
            findings.extend(scan_added_line(path, line_no, text))

    missing_tests = _test_requirement_finding(cfg, code_files, test_files)
    if missing_tests:
        findings.append(missing_tests)

    commands_run: list[str] = []
    if run_commands:
        if not repo_root:
            findings.append(finding(INFO, "commands-skipped",
                                    "Lint/test commands skipped: --repo-root is required."))
        else:
            for label, key in (("lint", "lint"), ("test", "test")):
                command = (cfg.get("commands") or {}).get(key)
                if not command:
                    continue
                commands_run.append(f"{label}: {command}")
                result = _run_command(label, command, repo_root)
                if result:
                    findings.append(result)

    if any(f["severity"] == BLOCKER for f in findings):
        verdict = "fail"
    elif any(f["severity"] in (ERROR, WARNING) for f in findings):
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "repo": repo,
        "pr": pr.get("number"),
        "verdict": verdict,
        "findings": sorted(findings, key=lambda f: SEVERITY_RANK.get(f["severity"], 9)),
        "code_files": [classify.path_of(f) for f in code_files],
        "test_files": [classify.path_of(f) for f in test_files],
        "other_files": [classify.path_of(f) for f in other_files],
        "commands_run": commands_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze code changes in a PR")
    parser.add_argument("--pr-json", default="-", help="pr-fetch output file, or '-' for stdin")
    parser.add_argument("--repo-root", help="local checkout (needed to run lint/test commands)")
    parser.add_argument("--config-file", help="JSON config merged over defaults")
    parser.add_argument("--run-commands", action="store_true", help="run configured lint/test commands")
    parser.add_argument("--comment-out", help="write the rendered Markdown comment to this file")
    parser.add_argument("--summary", help="summary line for the comment")
    parser.add_argument("--guidelines", help="comma-separated list of applied guidelines")
    parser.add_argument("--findings-only", action="store_true", help="print only the findings JSON array")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.pr_json == "-" else Path(args.pr_json).read_text(encoding="utf-8-sig")
    pr = json.loads(raw)

    explicit = json.loads(Path(args.config_file).read_text(encoding="utf-8-sig")) if args.config_file else None
    cfg = config_mod.resolve(repo_root=args.repo_root, repo=pr.get("repo"), explicit=explicit)

    result = analyze(pr, cfg, repo_root=args.repo_root, run_commands=args.run_commands)

    applied = [g for g in (args.guidelines or "").split(",") if g]
    notes = None
    if result["commands_run"]:
        notes = "Commands run:\n" + "\n".join(f"- `{c}`" for c in result["commands_run"])
    result["comment"] = render.render_comment(
        skill="Code Review",
        verdict=result["verdict"],
        summary=args.summary,
        findings=result["findings"],
        guidelines=applied,
        notes=notes,
        marker=COMMENT_MARKER,
    )

    if args.comment_out:
        Path(args.comment_out).write_text(result["comment"], encoding="utf-8")

    if args.findings_only:
        json.dump(result["findings"], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
