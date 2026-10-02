# General branch & PR guidelines

Applies to every repository. Repo-specific guidelines (`.review/branch-guidelines.md`)
extend these rules and always take precedence.

## Branch naming

- Format: `<type>/<issue-number>-<slug>` (e.g. `feature/2-user-feedback`).
- Types: `feature`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.
- Derive the type from issue labels (bug -> `fix`, enhancement -> `feature`,
  documentation -> `docs`) or from a conventional title prefix.
- Slug: lowercase, words separated by `-`, no trailing separators, ~50 chars max.

## Branch contents

- A new branch starts **empty** at the base branch HEAD.
- Do not commit file changes as part of branch creation; that is a separate task.
- Never force-push and never overwrite an existing branch.

## Pull requests

- Base the PR on the same branch it was cut from (usually `main`).
- Title: the issue title, or a concise `<type>: summary`.
- Body: summary + context, and `Closes #<issue>` when an issue exists.
- Open as draft when the work is not ready for review.

## Safety

- Refuse to run on a dirty working tree unless explicitly allowed.
- Prefer `--dry-run` first to preview the branch name and PR settings.
- Creating a branch and opening a PR are the only remote writes; nothing else.
