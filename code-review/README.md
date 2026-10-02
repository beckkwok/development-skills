# code-review

Reviews a GitHub PR for code changes, posts a code review comment, and flags
missing tests or problems. Read-only on source.

## Files

- `SKILL.md` - agent instructions (workflow, verdict policy, guardrails).
- `references/general-guidelines.md` - rules applied to every repo.
- `scripts/code_checks.py` - analyzer + comment generator.

## Quick start

Replace `<skills-root>` with your skills directory (`~/.agents/skills`). Commands are
single-line and shell-neutral (POSIX shells and Windows PowerShell).

```bash
python "<skills-root>/_review-lib/cli.py" check
python "<skills-root>/_review-lib/cli.py" pr-fetch --repo owner/repo --pr 123 > /tmp/pr.json
python "<skills-root>/code-review/scripts/code_checks.py" --pr-json /tmp/pr.json --comment-out /tmp/code-comment.md --json
python "<skills-root>/_review-lib/cli.py" comment --repo owner/repo --number 123 --kind pr --body-file /tmp/code-comment.md
```

Add `--repo-root /path/to/checkout --run-commands` to run the repo's configured
`commands.lint` / `commands.test` (only on a trusted checkout).

## Checks

- **Blockers:** merge-conflict markers, committed secrets (placeholder-aware).
- **Errors:** missing tests (no test files), bare/`pass` exceptions, failed commands.
- **Warnings/notes:** debug leftovers, `eval`/`exec`, TODO/FIXME.

## Repo overrides (`.review/config.json`)

```json
{
  "require_tests": true,
  "commands": { "lint": "npm run lint", "test": "npm test" },
  "guidelines": { "code": ".review/code-guidelines.md" }
}
```
