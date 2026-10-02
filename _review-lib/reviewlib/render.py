"""Render review findings into a Markdown PR/issue comment."""

from __future__ import annotations

from typing import Any, Iterable

SEVERITIES = [
    ("blocker", "Blockers"),
    ("error", "Errors"),
    ("warning", "Warnings"),
    ("info", "Notes"),
]

VERDICT_LABELS = {
    "pass": "PASS",
    "passed": "PASS",
    "fail": "FAILED",
    "failed": "FAILED",
    "warn": "PASS WITH WARNINGS",
    "warning": "PASS WITH WARNINGS",
}


def verdict_label(verdict: Any) -> str:
    if isinstance(verdict, bool):
        return "PASS" if verdict else "FAILED"
    return VERDICT_LABELS.get(str(verdict).lower(), str(verdict).upper())


def render_findings(findings: Iterable[dict[str, Any]] | None) -> str:
    findings = list(findings or [])
    if not findings:
        return "_No issues found._"

    lines: list[str] = []
    for severity, title in SEVERITIES:
        items = [f for f in findings if str(f.get("severity", "info")).lower() == severity]
        if not items:
            continue
        lines.append(f"**{title}**")
        for finding in items:
            location = finding.get("file", "") or ""
            if location and finding.get("line"):
                location = f"{location}:{finding['line']}"
            message = str(finding.get("message", "")).strip()
            bullet = f"- `{location}` - {message}" if location else f"- {message}"
            if finding.get("rule"):
                bullet += f" _(rule: {finding['rule']})_"
            lines.append(bullet)
            if finding.get("detail"):
                lines.append(f"  - {str(finding['detail']).strip()}")
        lines.append("")
    return "\n".join(lines).strip()


def render_comment(
    *,
    skill: str,
    verdict: Any,
    summary: str | None = None,
    findings: Iterable[dict[str, Any]] | None = None,
    guidelines: Iterable[str] | None = None,
    notes: str | None = None,
    marker: str | None = None,
) -> str:
    """Build a complete Markdown comment body."""
    lines: list[str] = [f"## {skill}: {verdict_label(verdict)}", ""]
    if summary:
        lines += [str(summary).strip(), ""]
    if guidelines:
        applied = ", ".join(f"`{g}`" for g in guidelines)
        lines += [f"Guidelines applied: {applied}", ""]
    lines += [render_findings(findings), ""]
    if notes:
        lines += ["---", "", str(notes).strip(), ""]
    if marker:
        lines += [marker]
    return "\n".join(lines).rstrip() + "\n"
