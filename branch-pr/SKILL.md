---
name: branch-pr
description: Create a new branch from main, push it, and open a pull request from it (optionally linked to an issue). Use when asked to "create a branch", "branch from main", "open a PR for this issue", "cut a feature branch", or "start a PR".
---

# Branch + PR Skill

Creates a branch off a base branch (default `main`), pushes it, and opens a pull
request from it. The branch is **empty** - it points at the base HEAD and contains
no file changes. This is a write skill, so it refuses to overwrite existing
branches or force-push.

## Paths

- `SKILL_DIR` - this skill's base directory.
- `SKILLS_ROOT` - the parent of `SKILL_DIR` (contains `_review-lib/`).

## Prerequisites

- GitHub CLI installed and authenticated (`check` below).
- A local checkout of the repo (`--repo-root`), or a directory to clone into (`--clone-dir`).

## Workflow

### 1. Verify GitHub access

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" check
```

### 2. Preview the plan (always do this first)

```bash
python "<SKILL_DIR>/scripts/branch_pr.py" --repo <owner/repo> --issue <N> \
  --repo-root "<path-to-checkout>" --dry-run --json
```

This shows the derived branch name (`<type>/<issue>-<slug>`), base branch, PR
title, reviewers and assignees - without changing anything.

### 3. Create the branch and open the PR

```bash
python "<SKILL_DIR>/scripts/branch_pr.py" --repo <owner/repo> --issue <N> \
  --repo-root "<path-to-checkout>" \
  [--base main] [--branch custom/name] [--type feature] \
  [--title "PR title"] [--body-file "<TMP>/pr-body.md"] \
  [--draft] [--reviewer alice,bob] [--assignee alice] --json
```

Without a checkout, clone on the fly:

```bash
python "<SKILL_DIR>/scripts/branch_pr.py" --repo <owner/repo> --issue <N> \
  --clone-dir "<TMP>/<repo-name>" --json
```

## Behavior

- **Base:** `main` by default; if absent, falls back to the repo default branch
  (an explicit `--base` that does not exist is an error).
- **Branch name:** `<type>/<issue-number>-<slug>` derived from the issue labels
  and title; override with `--branch`.
- **PR title/body:** from the issue (with `Closes #<N>`); override with
  `--title`/`--body-file`.
- **Assign:** `--reviewer` and `--assignee` are passed to `gh pr create`.
- **Empty branches:** GitHub cannot open a PR with zero commits, so pass
  `--empty-commit` to add one empty bootstrap commit (no file changes).

## Guardrails

- Never commit file changes; the branch starts empty at the base HEAD.
- Never force-push; refuse to overwrite an existing local or remote branch.
- Refuse a dirty working tree unless `--allow-dirty` is given.
- Always run `--dry-run` first and confirm the branch name and PR settings.
