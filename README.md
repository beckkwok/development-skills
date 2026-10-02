# development-skills

Portable agent skills for GitHub PR and issue workflows. Each skill is an
Anthropic-style `SKILL.md` folder and works wherever that format is supported.

## Contents

- `db-review/` — review PR database/schema changes, post a comment, update the schema registry on PASS.
- `code-review/` — review PR code changes, post a comment, flag missing tests/problems.
- `debug-analysis/` — analyze a GitHub issue, answer whether the bug makes sense and whether it can be reproduced, post the analysis, assign and label the issue.
- `branch-pr/` — create a branch from `main`, push it, and open a linked PR.
- `qa-verify/` — independently verify completed work against an issue and post a QA report with proof.
- `_review-lib/` — shared dependency-free Python helpers and CLI used by the skills. It is not a skill.

## Requirements

- Python 3.9+
- GitHub CLI (`gh`) installed and authenticated: `gh auth login`

## Install

Copy these folders into an auto-loaded skills directory while preserving their
relative layout:

```text
<skills-root>/
  _review-lib/
  db-review/
  code-review/
  debug-analysis/
  branch-pr/
  qa-verify/
```

`_review-lib/` must remain a sibling of the skill folders because the skills call
`../_review-lib/cli.py`.

## Safety model

- `db-review`, `code-review`, and `debug-analysis` are read-only on repository source.
- `debug-analysis` may add issue comments, assignees, and labels.
- `branch-pr` is write-capable: it pushes a new empty branch and opens a PR. It never commits file changes, force-pushes, or overwrites an existing branch.
- `qa-verify` runs tests and posts QA reports; it never modifies source and never fabricates evidence.

See each skill’s `SKILL.md` for the exact workflow.
