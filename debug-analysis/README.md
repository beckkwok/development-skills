# debug-analysis

Analyzes a GitHub issue and answers two questions, then posts the result,
assigns it to the author, and labels it:
1. Does the bug make sense?
2. Can we reproduce it?

Read-only on source; throwaway reproduction scripts go outside the repo.

## Files

- `SKILL.md` - agent instructions (workflow, analysis schema, guardrails).
- `references/general-guidelines.md` - analysis rules applied to every repo.
- `scripts/issue_checks.py` - `extract` and `render` commands.

## Quick start

```bash
SKILLS=~/.agents/skills
python "$SKILLS/_review-lib/cli.py" check
python "$SKILLS/_review-lib/cli.py" issue-fetch --repo owner/repo --issue 7 > /tmp/issue.json
python "$SKILLS/debug-analysis/scripts/issue_checks.py" extract \
  --issue-json /tmp/issue.json --repo-root /path/to/checkout --json

# after investigating and writing /tmp/analysis.json:
python "$SKILLS/debug-analysis/scripts/issue_checks.py" render \
  --issue-json /tmp/issue.json --analysis /tmp/analysis.json \
  --comment-out /tmp/debug-comment.md
python "$SKILLS/_review-lib/cli.py" comment --repo owner/repo --number 7 \
  --kind issue --body-file /tmp/debug-comment.md

# assign back to the author and label (bug | enhancement | invalid | needs-info | question)
python "$SKILLS/_review-lib/cli.py" issue-edit --repo owner/repo --number 7 \
  --assignee <author-login> --label issue-analysed --label bug --ensure-labels
```

## `analysis.json` shape

```json
{
  "summary": "...",
  "confidence": "high|medium|low",
  "makes_sense": { "verdict": "yes|no|unclear", "reasoning": "file:line trace" },
  "reproducible": { "verdict": "yes|no|unknown", "method": "...", "command": "...", "evidence": "..." },
  "next_steps": ["..."]
}
```

Never fabricate evidence - use `unknown` when reproduction was not attempted.
