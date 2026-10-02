# branch-pr

Creates a branch off a base branch (default `main`), pushes it, and opens a pull
request from it. The branch starts empty unless `--empty-commit` is given.

## Files

- `SKILL.md` - agent instructions (workflow, naming, guardrails).
- `references/general-guidelines.md` - branch and PR conventions for every repo.
- `scripts/branch_pr.py` - branch/PR creator.

## Quick start

Replace `<skills-root>` with your skills directory (`~/.agents/skills`). Commands are
single-line and shell-neutral (POSIX shells and Windows PowerShell).

```bash
python "<skills-root>/_review-lib/cli.py" check
```

Preview first (no changes):

```bash
python "<skills-root>/branch-pr/scripts/branch_pr.py" --repo owner/repo --issue 2 --repo-root /path/to/checkout --dry-run --json
```

Create the branch and open a draft PR:

```bash
python "<skills-root>/branch-pr/scripts/branch_pr.py" --repo owner/repo --issue 2 --repo-root /path/to/checkout --draft --empty-commit --json
```

Without a checkout, clone on the fly with `--clone-dir <dir>` instead of `--repo-root`.

## Behavior

- Branch name: `<type>/<issue-number>-<slug>` (e.g. `feature/2-user-feedback`);
  override with `--branch`.
- PR title/body default to the issue (with `Closes #N`); override with
  `--title` / `--body-file`.
- `--reviewer` / `--assignee` are passed to `gh pr create`.
- `--empty-commit` adds one empty bootstrap commit so GitHub can open the PR;
  without it, the branch points at the base HEAD unchanged.

## Guardrails

- Never commits file changes; never force-pushes.
- Refuses to overwrite an existing branch or run on a dirty tree (unless `--allow-dirty`).
