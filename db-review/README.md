# db-review

Reviews a GitHub PR for database/schema changes, posts a DB review comment, and
(on PASS) updates the repo's schema registry. Read-only on source and data.

## Files

- `SKILL.md` - agent instructions (workflow, verdict policy, guardrails).
- `references/general-guidelines.md` - rules applied to every repo.
- `references/registry-template.md` - schema registry document template.
- `scripts/db_checks.py` - analyzer + comment/registry generator.

## Quick start

Replace `<skills-root>` with your skills directory (`~/.agents/skills`). Commands are
single-line and shell-neutral (POSIX shells and Windows PowerShell).

```bash
python "<skills-root>/_review-lib/cli.py" check
python "<skills-root>/_review-lib/cli.py" pr-fetch --repo owner/repo --pr 123 > /tmp/pr.json
python "<skills-root>/db-review/scripts/db_checks.py" --pr-json /tmp/pr.json --repo-root /path/to/checkout --comment-out /tmp/db-comment.md --json
python "<skills-root>/_review-lib/cli.py" comment --repo owner/repo --number 123 --kind pr --body-file /tmp/db-comment.md
```

On PASS, add `--update-registry` (requires `--repo-root`) to append the entry to
`docs/db/schema-registry.md`.

## Verdicts

- `pass` - no issues; registry updated.
- `warn` - warnings only; registry update allowed.
- `fail` - any blocker (destructive DDL, missing rollback, secrets); registry unchanged.

A **missing rollback script** posts a comment marked **FAILED**; it is never generated.

## Repo overrides (`.review/config.json`)

```json
{
  "db_globs": ["db/migrate/**", "**/*.sql"],
  "registry": "docs/db/schema-registry.md",
  "require_rollback": true,
  "guidelines": { "db": ".review/db-guidelines.md" }
}
```
