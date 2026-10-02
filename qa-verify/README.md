# qa-verify

Verifies completed coding work against a GitHub issue and posts the QA result as
an issue comment with step-by-step proof. Independent: needs only repo + issue,
so it can run on a different machine or model than the coding agent.

## Files

- `SKILL.md` - agent instructions (workflow, verdicts, guardrails).
- `references/general-guidelines.md` - QA rules applied to every repo.
- `scripts/qa_checks.py` - `resolve`, `run`, and `render` commands.

## Quick start

```bash
SKILLS=~/.agents/skills
python "$SKILLS/_review-lib/cli.py" check
python "$SKILLS/_review-lib/cli.py" issue-fetch --repo owner/repo --issue 7 > /tmp/issue.json
python "$SKILLS/qa-verify/scripts/qa_checks.py" resolve --repo owner/repo --issue 7 \
  --repo-root /path/to/checkout

# record each verification step
python "$SKILLS/qa-verify/scripts/qa_checks.py" run --repo-root /path/to/checkout \
  --step "unit tests" --out /tmp/results.json -- "npm test"

# after judging criteria into /tmp/results.json, render and post
python "$SKILLS/qa-verify/scripts/qa_checks.py" render --issue-json /tmp/issue.json \
  --results /tmp/results.json --comment-out /tmp/qa-comment.md
python "$SKILLS/_review-lib/cli.py" comment --repo owner/repo --number 7 \
  --kind issue --body-file /tmp/qa-comment.md
```

## Verdicts

- `QA PASS` - every criterion verified, every step green.
- `QA FAIL` - any criterion failed or any step non-zero.
- `QA INCONCLUSIVE` - anything unverified or nothing executed.

## Screenshots

Add `{caption, url}` entries to `results.screenshots` for hosted images (embedded),
or `{caption, path}` for local files (listed for manual upload). Only real captures.
