#!/usr/bin/env python3
"""Static DB-change analysis for a pull request.

Reads the JSON produced by ``_review-lib/cli.py pr-fetch``, classifies the DB
relevant files, scans added lines for risky schema operations, checks for
rollback scripts, and (optionally) updates the schema registry document.

This script never modifies migrations, source, or data. When ``--update-registry``
is given it only writes the registry document (inside a local checkout).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "_review-lib"))

from reviewlib import classify, config as config_mod, files, render  # noqa: E402

COMMENT_MARKER = "<!-- db-review-agent -->"

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
# Diff parsing
# --------------------------------------------------------------------------- #

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_ADD_COLUMN_RE = re.compile(r"\bADD\s+(?:COLUMN\s+)?", re.I)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.I)
_DEFAULT_RE = re.compile(r"\bDEFAULT\b", re.I)


def iter_added_lines(patch: str) -> Iterable[tuple[int, str]]:
    """Yield ``(new_line_number, text)`` for every added line in a unified diff."""
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


DOWN_MARKER_RE = re.compile(r"^\s*--\s*(?:\+migrate\s+down|down|rollback|undo|revert)\b", re.I)
_UPGRADE_RE = re.compile(r"def\s+upgrade\s*\(")
_DOWNGRADE_RE = re.compile(r"def\s+downgrade\s*\(")


def forward_lines(path: str, patch: str) -> list[tuple[int, str]]:
    """Added lines that belong to the forward migration only.

    Stops at an SQL down-section marker and, for Alembic-style Python, scans
    only the ``upgrade()`` body so rollback code is never flagged.
    """
    lines = list(iter_added_lines(patch))
    kind = migration_kind(path)
    if kind in ("sql", "flyway"):
        forward: list[tuple[int, str]] = []
        for line_no, text in lines:
            if DOWN_MARKER_RE.match(text):
                break
            forward.append((line_no, text))
        return forward
    if kind == "python":
        start: int | None = None
        end = len(lines)
        for index, (_, text) in enumerate(lines):
            if _UPGRADE_RE.search(text):
                start = index
            elif _DOWNGRADE_RE.search(text) and start is not None:
                end = index
                break
        return lines[start:end] if start is not None else lines
    return lines


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #

DESTRUCTIVE_RE = re.compile(
    r"\bDROP\s+(?:TABLE|COLUMN|DATABASE|SCHEMA|INDEX|CONSTRAINT|VIEW|FUNCTION|TRIGGER|TYPE)\b",
    re.I,
)
TRUNCATE_RE = re.compile(r"\bTRUNCATE\b", re.I)
DELETE_FROM_RE = re.compile(r"\bDELETE\s+FROM\b", re.I)
WHERE_RE = re.compile(r"\bWHERE\b", re.I)
FK_RE = re.compile(r"\b(?:FOREIGN\s+KEY|REFERENCES)\b", re.I)
ALTER_TYPE_RE = re.compile(r"\bALTER\s+COLUMN\b[^;]*\bTYPE\b|\bMODIFY\s+COLUMN\b", re.I)
CREATE_INDEX_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.I)
CREATE_INDEX_IF_NOT_EXISTS_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b", re.I)
CONCURRENTLY_RE = re.compile(r"\bCONCURRENTLY\b", re.I)
RENAME_RE = re.compile(r"\bRENAME\s+(?:COLUMN|TABLE|TO)\b", re.I)
CASCADE_RE = re.compile(r"\bON\s+DELETE\s+CASCADE\b", re.I)
SET_NOT_NULL_RE = re.compile(r"\bALTER\s+COLUMN\b[^;]*\bSET\s+NOT\s+NULL\b", re.I)
CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\b(?!\s+IF\s+NOT\s+EXISTS)", re.I)
SECRET_RE = re.compile(
    r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\b"
    r"\s*[:=]\s*['\"][^'\"]{4,}['\"]",
    re.I,
)


def scan_added_line(path: str, line_no: int, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    if DESTRUCTIVE_RE.search(text):
        findings.append(finding(
            BLOCKER, "destructive-ddl", "Destructive DDL (DROP). Requires an explicit rollback plan.",
            path, line_no,
        ))
    if TRUNCATE_RE.search(text):
        findings.append(finding(BLOCKER, "truncate", "TRUNCATE removes all rows and is not reversible.", path, line_no))
    if DELETE_FROM_RE.search(text) and not WHERE_RE.search(text):
        findings.append(finding(
            BLOCKER, "delete-without-where", "DELETE FROM without a WHERE clause deletes every row.",
            path, line_no,
        ))
    if _ADD_COLUMN_RE.search(text) and _NOT_NULL_RE.search(text) and not _DEFAULT_RE.search(text):
        findings.append(finding(
            ERROR, "add-not-null-no-default",
            "Adding a NOT NULL column without a DEFAULT fails on non-empty tables.",
            path, line_no,
        ))
    if SET_NOT_NULL_RE.search(text):
        findings.append(finding(
            WARNING, "set-not-null", "SET NOT NULL takes an ACCESS EXCLUSIVE lock and scans the table.",
            path, line_no,
        ))
    if ALTER_TYPE_RE.search(text):
        findings.append(finding(
            WARNING, "alter-type", "Changing a column type can rewrite the table and lock it.",
            path, line_no,
        ))
    if CREATE_INDEX_RE.search(text) and not CONCURRENTLY_RE.search(text) and "IF NOT EXISTS" not in text.upper():
        findings.append(finding(
            WARNING, "create-index-lock", "CREATE INDEX without CONCURRENTLY locks writes on the table.",
            path, line_no,
        ))
    elif CREATE_INDEX_RE.search(text) and not CONCURRENTLY_RE.search(text):
        findings.append(finding(
            INFO, "create-index-lock", "CREATE INDEX IF NOT EXISTS without CONCURRENTLY locks writes.",
            path, line_no,
        ))
    if FK_RE.search(text):
        findings.append(finding(
            INFO, "fk-index", "Foreign key added - confirm the referencing column is indexed.",
            path, line_no,
        ))
    if RENAME_RE.search(text):
        findings.append(finding(
            WARNING, "rename", "Renaming a column/table breaks code depending on the old name.",
            path, line_no,
        ))
    if CASCADE_RE.search(text):
        findings.append(finding(
            WARNING, "on-delete-cascade", "ON DELETE CASCADE can silently delete related rows.",
            path, line_no,
        ))
    if CREATE_TABLE_RE.search(text):
        findings.append(finding(
            INFO, "create-table", "CREATE TABLE without IF NOT EXISTS is not idempotent.",
            path, line_no,
        ))
    if SECRET_RE.search(text):
        findings.append(finding(
            BLOCKER, "secret-literal", "Possible secret/credential literal committed in a migration.",
            path, line_no,
        ))
    return findings


# --------------------------------------------------------------------------- #
# Rollback detection
# --------------------------------------------------------------------------- #

FLYWAY_RE = re.compile(r"/V\d+[^/]*__[^/]*\.sql$", re.I)
MIGRATION_RE = re.compile(
    r"(?:^|/)(?:migrations?|migrate|alembic|flyway|liquibase)(?:/|$)|/V\d+[^/]*__[^/]*\.sql$",
    re.I,
)
ROLLBACK_SUFFIXES = (".down.sql", ".rollback.sql", ".undo.sql", ".revert.sql")


def migration_kind(path: str) -> str:
    low = path.lower()
    if FLYWAY_RE.search("/" + path):
        return "flyway"
    if low.endswith(".sql"):
        return "sql"
    if low.endswith(".py"):
        return "python"
    if low.endswith(".rb"):
        return "rails"
    if low.endswith((".js", ".ts", ".mjs", ".cjs")):
        return "node"
    return "other"


def is_migration(path: str) -> bool:
    return bool(MIGRATION_RE.search("/" + path.replace("\\", "/")))


def _content_rollback(kind: str, path: str, content: str) -> str | None:
    if kind == "python":
        match = re.search(r"def\s+downgrade\s*\([^)]*\):(.*?)(?=\ndef |\Z)", content, re.S)
        if match and match.group(1).strip() not in ("", "pass"):
            return f"{path} (downgrade)"
    if kind == "rails":
        if re.search(r"def\s+down\b", content) or re.search(r"\breversible\b", content):
            return f"{path} (down/reversible)"
        if re.search(r"def\s+change\b", content):
            if re.search(r"\bexecute\b", content):
                return None
            return f"{path} (reversible change)"
    if kind in ("node",):
        if re.search(r"(?i)\b(?:down|rollback|undo|revert)\s*[:(=]", content):
            return f"{path} (rollback fn)"
    if kind in ("sql", "flyway"):
        if re.search(r"(?im)^\s*--\s*\+migrate\s+down\b", content):
            return f"{path} (goose down)"
        if re.search(r"(?im)^\s*--\s*(?:down|rollback|undo|revert)\b", content):
            return f"{path} (down section)"
    return None


def find_rollback(
    path: str,
    patch: str,
    changed_paths: set[str],
    repo_root: str | None,
) -> str | None:
    kind = migration_kind(path)
    posix = path.replace("\\", "/")

    candidates: list[str] = []
    if kind == "flyway":
        name = posixpath.basename(posix)
        candidates.append(posixpath.join(posixpath.dirname(posix), "U" + name[1:]))
    else:
        base, _ = posixpath.splitext(posix)
        candidates.extend(base + suffix for suffix in ROLLBACK_SUFFIXES)

    for candidate in candidates:
        if candidate in changed_paths:
            return candidate
        if repo_root and (Path(repo_root) / candidate).is_file():
            return candidate

    added = "\n".join(text for _, text in iter_added_lines(patch))
    return _content_rollback(kind, posix, added)


# --------------------------------------------------------------------------- #
# Schema change summary
# --------------------------------------------------------------------------- #

TABLE_OP_RES = [
    (re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\".]+)", re.I), "create table"),
    (re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w\".]+)", re.I), "drop table"),
    (re.compile(r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w\".]+)", re.I), "alter table"),
    (re.compile(r"\bADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\".]+)", re.I), "add column"),
    (re.compile(r"\bDROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?([\w\".]+)", re.I), "drop column"),
    (re.compile(r"\bRENAME\s+COLUMN\s+([\w\".]+)\s+TO\s+([\w\".]+)", re.I), "rename column"),
    (re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([\w\".]+)", re.I), "create index"),
]


def summarize_changes(db_files: list[dict[str, Any]]) -> list[str]:
    summary: list[str] = []
    seen: set[str] = set()
    for entry in db_files:
        path = classify.path_of(entry)
        patch = entry.get("patch") if isinstance(entry, dict) else None
        if not patch:
            continue
        for _, text in forward_lines(path, patch):
            for regex, verb in TABLE_OP_RES:
                match = regex.search(text)
                if match:
                    target = " -> ".join(match.groups())
                    label = f"{verb} `{target}` (`{path}`)"
                    if label not in seen:
                        seen.add(label)
                        summary.append(label)
    return summary


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def _author(meta: dict[str, Any]) -> str:
    author = meta.get("author")
    if isinstance(author, dict):
        return author.get("login", "unknown")
    return str(author or "unknown")


def build_registry_entry(
    repo: str,
    pr_number: int,
    meta: dict[str, Any],
    db_files: list[dict[str, Any]],
    migration_scripts: list[str],
    rollback_scripts: list[str],
    schema_changes: list[str],
    risks: list[str],
    verdict: str = "pass",
) -> str:
    start = f"<!-- db-registry:start PR#{pr_number} -->"
    end = f"<!-- db-registry:end PR#{pr_number} -->"
    lines = [
        start,
        f"### PR #{pr_number}: {meta.get('title', '')}".rstrip(),
        "",
        f"- **Repo:** {repo}",
        f"- **PR:** {meta.get('url', '')}",
        f"- **Author:** {_author(meta)}",
        f"- **Reviewed:** {_dt.date.today().isoformat()}",
        f"- **Status:** {verdict.upper()}",
        "",
        "**DB files**",
    ]
    lines += [f"- `{classify.path_of(f)}`" for f in db_files] or ["- _(none)_"]
    lines += ["", "**Schema changes**"]
    lines += [f"- {c}" for c in schema_changes] or ["- _(none detected)_"]
    lines += ["", "**Migration scripts**"]
    lines += [f"- `{s}`" for s in migration_scripts] or ["- _(none)_"]
    lines += ["", "**Rollback scripts**"]
    lines += [f"- `{s}`" for s in rollback_scripts] or ["- _(none)_"]
    lines += ["", "**Risk notes**"]
    lines += [f"- {r}" for r in risks] or ["- _(none)_"]
    lines += ["", end]
    return "\n".join(lines)


def update_registry(repo_root: str, registry_path: str, pr_number: int, entry: str) -> Path:
    target = Path(repo_root) / registry_path
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = files.read_text(target) if target.is_file() else "# DB Schema Registry\n"
    start = f"<!-- db-registry:start PR#{pr_number} -->"
    end = f"<!-- db-registry:end PR#{pr_number} -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if pattern.search(existing):
        updated = pattern.sub(entry, existing)
    else:
        updated = existing.rstrip() + "\n\n" + entry + "\n"
    target.write_text(updated, encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def analyze(pr: dict[str, Any], cfg: dict[str, Any], repo_root: str | None = None) -> dict[str, Any]:
    repo = pr.get("repo", "")
    meta = pr.get("meta", {})
    files = pr.get("files", [])
    grouped = classify.classify_files(files, cfg)
    db_files = grouped["db"]
    changed_paths = {classify.path_of(f).replace("\\", "/") for f in files}

    findings: list[dict[str, Any]] = []
    migration_scripts: list[str] = []
    rollback_scripts: list[str] = []

    for entry in db_files:
        path = classify.path_of(entry)
        patch = entry.get("patch") if isinstance(entry, dict) else None
        if not patch:
            findings.append(finding(
                INFO, "no-patch",
                "File changed but GitHub did not return a patch (binary or too large) - review manually.",
                path,
            ))
        else:
            for line_no, text in forward_lines(path, patch):
                findings.extend(scan_added_line(path, line_no, text))

        if is_migration(path):
            migration_scripts.append(path)
            rollback = find_rollback(path, patch or "", changed_paths, repo_root)
            if rollback:
                rollback_scripts.append(rollback)
            else:
                severity = BLOCKER if cfg.get("require_rollback", True) else WARNING
                findings.append(finding(
                    severity, "missing-rollback",
                    "No rollback/undo script found for this migration.",
                    path,
                    detail="Add a down/undo migration (or set require_rollback=false in .review/config.json if forward-only).",
                ))

    schema_changes = summarize_changes(db_files)
    risks = [f"{f['message']} ({f.get('file', '?')})" for f in findings
             if f["severity"] in (BLOCKER, ERROR)]

    if any(f["severity"] == BLOCKER for f in findings):
        verdict = "fail"
    elif any(f["severity"] in (ERROR, WARNING) for f in findings):
        verdict = "warn"
    else:
        verdict = "pass"

    registry_entry = build_registry_entry(
        repo, pr.get("number", 0), meta, db_files,
        migration_scripts, rollback_scripts, schema_changes, risks, verdict,
    )

    return {
        "repo": repo,
        "pr": pr.get("number"),
        "verdict": verdict,
        "findings": sorted(findings, key=lambda f: SEVERITY_RANK.get(f["severity"], 9)),
        "db_files": [classify.path_of(f) for f in db_files],
        "migration_scripts": migration_scripts,
        "rollback_scripts": rollback_scripts,
        "schema_changes": schema_changes,
        "registry_entry": registry_entry,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze DB changes in a PR")
    parser.add_argument("--pr-json", default="-", help="pr-fetch output file, or '-' for stdin")
    parser.add_argument("--repo-root", help="local checkout (for rollback lookup and registry update)")
    parser.add_argument("--config-file", help="JSON config merged over defaults")
    parser.add_argument("--registry", help="override registry path")
    parser.add_argument("--update-registry", action="store_true", help="write the registry entry on PASS")
    parser.add_argument("--entry-only", action="store_true", help="print only the registry entry markdown")
    parser.add_argument("--findings-only", action="store_true", help="print only the findings JSON array")
    parser.add_argument("--comment-out", help="write the rendered Markdown comment to this file")
    parser.add_argument("--summary", help="summary line for the comment")
    parser.add_argument("--guidelines", help="comma-separated list of applied guidelines")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.pr_json == "-" else files.read_text(args.pr_json)
    pr = json.loads(raw)

    explicit = json.loads(files.read_text(args.config_file)) if args.config_file else None
    cfg = config_mod.resolve(repo_root=args.repo_root, repo=pr.get("repo"), explicit=explicit)

    result = analyze(pr, cfg, repo_root=args.repo_root)

    registry_path = args.registry or cfg.get("registry", "docs/db/schema-registry.md")
    if args.update_registry:
        if not args.repo_root:
            result["registry_updated"] = False
            result["registry_note"] = "--repo-root is required to update the registry."
        elif result["verdict"] == "pass":
            target = update_registry(args.repo_root, registry_path, result["pr"], result["registry_entry"])
            result["registry_updated"] = True
            result["registry_path"] = str(target)
        else:
            result["registry_updated"] = False
            result["registry_note"] = "Review did not pass; registry left unchanged."

    applied = [g for g in (args.guidelines or "").split(",") if g]
    comment = render.render_comment(
        skill="DB Review",
        verdict=result["verdict"],
        summary=args.summary,
        findings=result["findings"],
        guidelines=applied,
        notes=result.get("registry_note"),
        marker=COMMENT_MARKER,
    )
    result["comment"] = comment

    if args.comment_out:
        Path(args.comment_out).write_text(comment, encoding="utf-8")

    if args.entry_only:
        sys.stdout.write(result["registry_entry"] + "\n")
    elif args.findings_only:
        json.dump(result["findings"], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
