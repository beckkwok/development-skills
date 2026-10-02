#!/usr/bin/env python3
"""Command-line entrypoint for the review skills.

Run as::

    python <skills-root>/_review-lib/cli.py <command> [options]

Commands are deliberately small and JSON-first so a skill's SKILL.md can chain
them without embedding logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reviewlib import classify, config as config_mod, files, gh, guidelines, render  # noqa: E402

SKILLS_ROOT = Path(__file__).resolve().parent.parent


def _emit(obj: object) -> None:
    json.dump(obj, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _read_text(path: str | None) -> str:
    if path in (None, "-"):
        return sys.stdin.read()
    return files.read_text(path)


def _explicit(args: argparse.Namespace) -> dict:
    cfg: dict = {}
    if getattr(args, "config_file", None):
        cfg = json.loads(files.read_text(args.config_file))
    return cfg


def _resolve(args: argparse.Namespace, *, repo: str | None, ref: str | None) -> dict:
    return config_mod.resolve(
        repo_root=getattr(args, "repo_root", None),
        repo=None if getattr(args, "no_repo_config", False) else repo,
        ref=ref,
        explicit=_explicit(args),
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config-file", help="JSON file merged over defaults")
    parser.add_argument("--repo-root", help="local checkout to read config/guidelines from")
    parser.add_argument("--no-repo-config", action="store_true", help="ignore the repo's .review/config.json")


def cmd_check(_: argparse.Namespace) -> None:
    _emit(gh.check_auth())


def cmd_pr_fetch(args: argparse.Namespace) -> None:
    _emit(gh.pr_fetch(args.repo, args.pr, include_diff=not args.no_diff))


def cmd_issue_fetch(args: argparse.Namespace) -> None:
    _emit(gh.issue_fetch(args.repo, args.issue))


def cmd_classify(args: argparse.Namespace) -> None:
    data = gh.pr_fetch(args.repo, args.pr, include_diff=False)
    ref = data["meta"].get("headRefOid")
    cfg = _resolve(args, repo=data["repo"], ref=ref)
    grouped = classify.classify_files(data["files"], cfg)
    _emit(
        {
            "repo": data["repo"],
            "pr": args.pr,
            "head_ref": ref,
            "counts": {key: len(value) for key, value in grouped.items()},
            "files": {key: [classify.path_of(f) for f in value] for key, value in grouped.items()},
        }
    )


def cmd_guidelines(args: argparse.Namespace) -> None:
    skill_dir = Path(args.skill_dir) if args.skill_dir else SKILLS_ROOT / args.skill
    cfg = _resolve(args, repo=args.repo, ref=args.ref)
    data = guidelines.load_merged(
        skill_dir=skill_dir,
        key=args.key,
        repo_root=args.repo_root,
        repo=args.repo,
        ref=args.ref,
        cfg=cfg,
    )
    if args.json:
        _emit(data)
    else:
        sys.stdout.write(data["combined"])


def cmd_comment(args: argparse.Namespace) -> None:
    body = _read_text(args.body_file)
    print(gh.comment_post(args.repo, args.number, body, kind=args.kind))


def cmd_comment_update(args: argparse.Namespace) -> None:
    body = _read_text(args.body_file)
    print(gh.comment_update(args.repo, args.comment_id, body))


def cmd_find_comment(args: argparse.Namespace) -> None:
    _emit(gh.find_comment(args.repo, args.number, args.marker) or {})


def cmd_issue_edit(args: argparse.Namespace) -> None:
    created_labels: list[str] = []
    if args.ensure_labels:
        created_labels = gh.label_ensure(args.repo, args.label)
    url = gh.issue_edit(
        args.repo,
        args.number,
        add_assignees=args.assignee,
        add_labels=args.label,
    )
    _emit(
        {
            "url": url,
            "assignees": [a for a in args.assignee if a],
            "labels": [lbl for lbl in args.label if lbl],
            "ensured_labels": created_labels,
        }
    )


def cmd_render(args: argparse.Namespace) -> None:
    findings = json.loads(_read_text(args.findings))
    applied = [g for g in (args.guidelines or "").split(",") if g]
    body = render.render_comment(
        skill=args.skill,
        verdict=args.verdict,
        summary=args.summary,
        findings=findings,
        guidelines=applied,
        notes=_read_text(args.notes) if args.notes else None,
        marker=args.marker,
    )
    sys.stdout.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review-cli", description="Shared helpers for review skills")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="verify gh is installed and authenticated")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("pr-fetch", help="fetch PR metadata, files and diff as JSON")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--no-diff", action="store_true")
    p.set_defaults(func=cmd_pr_fetch)

    p = sub.add_parser("issue-fetch", help="fetch an issue as JSON")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", type=int, required=True)
    p.set_defaults(func=cmd_issue_fetch)

    p = sub.add_parser("classify", help="classify a PR's changed files")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", type=int, required=True)
    _add_common(p)
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("guidelines", help="print merged general + repo guidelines")
    p.add_argument("--skill", required=True, help="skill folder name, e.g. db-review")
    p.add_argument("--key", default="db", choices=["db", "code", "debug"])
    p.add_argument("--skill-dir", help="override the skill directory")
    p.add_argument("--repo", help="owner/repo to fetch repo guidelines from")
    p.add_argument("--ref", help="git ref (e.g. PR head sha)")
    p.add_argument("--json", action="store_true")
    _add_common(p)
    p.set_defaults(func=cmd_guidelines)

    p = sub.add_parser("comment", help="post a new PR/issue comment")
    p.add_argument("--repo", required=True)
    p.add_argument("--number", type=int, required=True)
    p.add_argument("--kind", default="pr", choices=["pr", "issue"])
    p.add_argument("--body-file", default="-", help="file with the body, or '-' for stdin")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("comment-update", help="edit an existing comment in place")
    p.add_argument("--repo", required=True)
    p.add_argument("--comment-id", type=int, required=True)
    p.add_argument("--body-file", default="-", help="file with the body, or '-' for stdin")
    p.set_defaults(func=cmd_comment_update)

    p = sub.add_parser("find-comment", help="find a comment containing a marker")
    p.add_argument("--repo", required=True)
    p.add_argument("--number", type=int, required=True)
    p.add_argument("--marker", required=True)
    p.set_defaults(func=cmd_find_comment)

    p = sub.add_parser("issue-edit", help="add assignees and/or labels to an issue")
    p.add_argument("--repo", required=True)
    p.add_argument("--number", type=int, required=True)
    p.add_argument("--assignee", action="append", default=[], help="repeatable GitHub login")
    p.add_argument("--label", action="append", default=[], help="repeatable label name")
    p.add_argument("--ensure-labels", action="store_true", help="create missing labels before applying")
    p.set_defaults(func=cmd_issue_edit)

    p = sub.add_parser("render", help="render findings JSON into a Markdown comment")
    p.add_argument("--skill", required=True, help="display title, e.g. 'DB Review'")
    p.add_argument("--verdict", required=True, help="pass|fail|warn")
    p.add_argument("--summary")
    p.add_argument("--findings", default="-", help="findings JSON file, or '-' for stdin")
    p.add_argument("--guidelines", help="comma-separated list of applied guidelines")
    p.add_argument("--notes", help="file with extra notes")
    p.add_argument("--marker", help="HTML marker appended to the body")
    p.set_defaults(func=cmd_render)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except gh.GhError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
