#!/usr/bin/env python3
"""Debug analysis for a GitHub issue.

Two modes:

- ``extract`` - parse the issue into structured fields (steps, expected, actual,
  environment, logs) and suggest relevant code locations.
- ``render``  - turn the agent's analysis JSON into a Markdown issue comment.

Read-only: this script never edits repository source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "_review-lib"))

from reviewlib import files  # noqa: E402

COMMENT_MARKER = "<!-- debug-analysis-agent -->"

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "env", "__pycache__",
    "target", "vendor", ".next", "coverage", ".idea", ".vscode", "bin", "obj",
}
MAX_FILES = 4000
MAX_FILE_BYTES = 1_000_000

SECTION_KEYWORDS = {
    "steps": ["steps to reproduce", "steps", "reproduction", "repro", "to reproduce", "how to reproduce"],
    "expected": ["expected behavior", "expected result", "expected"],
    "actual": ["actual behavior", "actual result", "actual", "what happened", "observed"],
    "environment": ["environment", "version", "os", "platform", "browser", "device", "setup"],
    "logs": ["logs", "log", "error", "traceback", "stack trace", "output"],
}

HEADING_RE = re.compile(r"^(?:#{1,6}\s+.+|\*\*.+\*\*:?|[A-Z][A-Za-z0-9 /_-]{2,60}:)\s*$")

IDENT_RE = re.compile(r"`([^`\n]{2,60})`")
CAMEL_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b")
SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
FILE_RE = re.compile(
    r"\b[\w./-]+\.(?:py|js|ts|tsx|jsx|rb|go|java|kt|kts|cs|php|rs|c|cc|cpp|h|hpp|sql|json|ya?ml|toml|md)\b"
)
FUNC_RE = re.compile(r"\b([a-z_][a-z0-9_]{2,})\s*\(")
PLAIN_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b")
COMMON_WORDS = {
    "the", "and", "for", "with", "this", "that", "when", "have", "has", "not", "but",
    "from", "into", "should", "would", "could", "will", "error", "issue", "expected",
    "actual", "return", "print", "true", "false", "none", "null", "test", "tests",
    "using", "get", "set", "run", "add", "new", "old", "value", "values", "code",
    "there", "their", "they", "them", "these", "those", "which", "what", "your", "yours",
    "then", "than", "also", "some", "such", "only", "over", "just", "like", "more",
    "most", "must", "need", "needs", "able", "after", "before", "being", "both", "each",
    "other", "same", "very", "well", "make", "made", "used", "does", "doing", "about",
    "where", "while", "here", "were", "been", "because", "between", "through", "during",
}


def _clean_heading(line: str) -> str:
    text = line.strip().strip("*#").strip()
    return text.rstrip(":").strip().lower()


def parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_KEYWORDS}
    current: str | None = None
    in_fence = False
    fence_lines: list[str] = []

    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            if not in_fence and fence_lines:
                sections["logs"].extend(fence_lines)
                fence_lines = []
            continue
        if in_fence:
            fence_lines.append(raw)
            continue

        if HEADING_RE.match(raw):
            heading = _clean_heading(raw)
            matched = None
            for key, keywords in SECTION_KEYWORDS.items():
                if any(heading.startswith(keyword) or keyword == heading for keyword in keywords):
                    matched = key
                    break
            current = matched
            if matched:
                # Keep the heading text itself out of the body.
                continue
        if current:
            sections[current].append(raw)

    return {key: "\n".join(lines).strip() for key, lines in sections.items() if "".join(lines).strip()}


def extract_keywords(text: str, limit: int = 24) -> list[str]:
    """Prefer code-like tokens, then fall back to significant prose words."""
    text = text or ""
    code_tokens: list[str] = []
    for regex in (IDENT_RE, FILE_RE, CAMEL_RE, SNAKE_RE, FUNC_RE):
        for match in regex.findall(text):
            token = match if isinstance(match, str) else match[0]
            token = token.strip().strip("`")
            if 2 <= len(token) <= 60:
                code_tokens.append(token)
    plain_tokens = PLAIN_WORD_RE.findall(text)

    seen: set[str] = set()
    ordered: list[str] = []
    for token in code_tokens + plain_tokens:
        low = token.lower()
        if low in COMMON_WORDS or low in seen or len(low) < 3:
            continue
        seen.add(low)
        ordered.append(token)
        if len(ordered) >= limit:
            break
    return ordered


def find_code_hits(repo_root: str, keywords: list[str], limit: int = 10) -> list[dict[str, Any]]:
    root = Path(repo_root)
    if not root.is_dir() or not keywords:
        return []

    lowered = [(kw, kw.lower()) for kw in keywords]
    scores: dict[str, int] = {}
    scanned = 0

    for path in root.rglob("*"):
        if scanned >= MAX_FILES:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        low = text.lower()
        score = sum(low.count(kw) for _, kw in lowered)
        if score:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path)
            scores[rel] = score

    top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{"file": name, "hits": count} for name, count in top]


def extract(issue: dict[str, Any], repo_root: str | None = None) -> dict[str, Any]:
    body = issue.get("body") or ""
    title = issue.get("title") or ""
    keywords = extract_keywords(f"{title}\n{body}")
    return {
        "repo": issue.get("_repo"),
        "number": issue.get("number"),
        "title": title,
        "url": issue.get("url"),
        "state": issue.get("state"),
        "author": (issue.get("author") or {}).get("login") if isinstance(issue.get("author"), dict) else issue.get("author"),
        "labels": [lbl.get("name") if isinstance(lbl, dict) else lbl for lbl in (issue.get("labels") or [])],
        "comments": len(issue.get("comments") or []),
        "sections": parse_sections(body),
        "keywords": keywords,
        "code_hits": find_code_hits(repo_root, keywords) if repo_root else [],
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _verdict_text(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    mapping = {"yes": "Yes", "no": "No", "true": "Yes", "false": "No", "unknown": "Unknown",
               "unclear": "Unclear", "partial": "Partially",
               "n/a": "Not applicable", "not-applicable": "Not applicable", "na": "Not applicable"}
    return mapping.get(str(value).lower(), str(value))


def render(issue: dict[str, Any], analysis: dict[str, Any], guidelines: list[str] | None = None) -> str:
    lines: list[str] = [f"## Debug Analysis: {issue.get('title', 'issue')}", ""]

    if analysis.get("summary"):
        lines += [str(analysis["summary"]).strip(), ""]
    lines += [f"- **Issue:** {issue.get('url', '')}", f"- **Confidence:** {_verdict_text(analysis.get('confidence', 'unknown'))}", ""]

    makes_sense = analysis.get("makes_sense", {})
    lines += ["### 1. Does the bug make sense?", ""]
    lines += [f"**{_verdict_text(makes_sense.get('verdict'))}**", ""]
    if makes_sense.get("reasoning"):
        lines += [str(makes_sense["reasoning"]).strip(), ""]

    reproducible = analysis.get("reproducible", {})
    lines += ["### 2. Can we reproduce it?", ""]
    lines += [f"**{_verdict_text(reproducible.get('verdict'))}**", ""]
    if reproducible.get("method"):
        lines += [str(reproducible["method"]).strip(), ""]
    if reproducible.get("command"):
        lines += ["```bash", str(reproducible["command"]).strip(), "```", ""]
    if reproducible.get("evidence"):
        lines += ["**Evidence**", "", "```", str(reproducible["evidence"]).strip(), "```", ""]

    if analysis.get("next_steps"):
        lines += ["### Suggested next steps", ""]
        lines += [f"- {step}" for step in analysis["next_steps"]]
        lines += [""]

    if guidelines:
        lines += [f"Guidelines applied: " + ", ".join(f"`{g}`" for g in guidelines), ""]

    lines += [COMMENT_MARKER]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug analysis for a GitHub issue")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_extract = sub.add_parser("extract", help="parse an issue into structured fields")
    p_extract.add_argument("--issue-json", default="-")
    p_extract.add_argument("--repo-root")
    p_extract.add_argument("--json", action="store_true")

    p_render = sub.add_parser("render", help="render the analysis into a comment")
    p_render.add_argument("--issue-json", default="-")
    p_render.add_argument("--analysis", required=True, help="analysis JSON file")
    p_render.add_argument("--comment-out")
    p_render.add_argument("--guidelines", help="comma-separated list of applied guidelines")

    args = parser.parse_args(argv)

    if args.mode == "extract":
        raw = sys.stdin.read() if args.issue_json == "-" else files.read_text(args.issue_json)
        issue = json.loads(raw)
        result = extract(issue, repo_root=args.repo_root)
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    raw_issue = sys.stdin.read() if args.issue_json == "-" else files.read_text(args.issue_json)
    issue = json.loads(raw_issue)
    analysis = json.loads(files.read_text(args.analysis))
    applied = [g for g in (args.guidelines or "").split(",") if g]
    body = render(issue, analysis, applied)
    if args.comment_out:
        Path(args.comment_out).write_text(body, encoding="utf-8")
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
