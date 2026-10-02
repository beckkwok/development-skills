---
name: code-review
description: Review a GitHub pull request for code changes, post a code review comment, and flag missing tests or problems. Use when asked to "code review", "review this PR", "vet a pull request", or check code changes for bugs, secrets, debug leftovers, or missing tests.
---

# Code Review Skill

Vets a GitHub PR for code changes and posts a review comment. It is **read-only on
source** - it never edits code, it only reads, comments, and (optionally) runs the
repo's configured lint/test commands.

## Paths

- `SKILL_DIR` - this skill's base directory.
- `SKILLS_ROOT` - the parent of `SKILL_DIR` (contains `_review-lib/`).
- `TMP` - any scratch directory (e.g. `$env:TEMP` on Windows, `/tmp` elsewhere).

Commands below are single-line and shell-neutral: they run unchanged in POSIX
shells and Windows PowerShell.

## Prerequisites

- GitHub CLI installed and authenticated: run the `check` command below.

## Workflow

### 1. Verify GitHub access

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" check
```

### 2. Fetch the PR

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" pr-fetch --repo <owner/repo> --pr <N> > "<TMP>/pr.json"
```

### 3. Load guidelines

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" guidelines --skill code-review --key code --repo <owner/repo> --ref <headRefOid> --json
```

- Use `--repo-root <path>` instead of `--repo/--ref` when working from a checkout.
- Pass the returned `sources` names to `--guidelines` so the comment records what applied.

### 4. Analyze

```bash
python "<SKILL_DIR>/scripts/code_checks.py" --pr-json "<TMP>/pr.json" --comment-out "<TMP>/code-comment.md" --summary "<one-line summary>" --guidelines "general[,repo-specific]" --json > "<TMP>/code-result.json"
```

Add `--repo-root "<path>" --run-commands` to run the repo's `commands.lint` /
`commands.test` (from `.review/config.json`). Only do this on a trusted checkout.

The result JSON has `verdict`, `findings`, `code_files`, `test_files`,
`other_files` and `commands_run`.

- **No `code_files`:** post a short PASS comment stating no code changes were found and stop.

### 5. Post the review comment

Post a **new** comment by default:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment --repo <owner/repo> --number <N> --kind pr --body-file "<TMP>/code-comment.md"
```

Only when the user asks to update in place:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" find-comment --repo <owner/repo> --number <N> --marker "<!-- code-review-agent -->"
```

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment-update --repo <owner/repo> --comment-id <id> --body-file "<TMP>/code-comment.md"
```

## Verdict policy

| Verdict | Meaning | Action |
| --- | --- | --- |
| `pass` | No blockers/errors/warnings | Comment PASS. |
| `warn` | Only errors/warnings | Comment "PASS WITH WARNINGS" and list what is missing. |
| `fail` | Any blocker (conflict markers, secrets) | Comment **FAILED** with itemized findings. |

Missing tests is reported as an **error** ("PASS WITH WARNINGS"). Tune with
`"require_tests": false` in `.review/config.json`.

## Guardrails

- Never modify source code or business logic - comment only.
- Only run lint/test commands when `--run-commands` is passed on a trusted checkout.
- Do not generate fixes; describe what is missing.
- Always append the marker `<!-- code-review-agent -->` so comments are identifiable.
