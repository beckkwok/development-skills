---
name: debug-analysis
description: Analyze a GitHub issue to decide whether the reported bug makes sense and whether it can be reproduced, then post the analysis as a comment, assign it back to the author, and label it. Use when asked to "analyze this bug", "debug analysis", "triage this issue", "can we reproduce this", or to investigate a GitHub issue.
---

# Debug Analysis Skill

Reads a GitHub issue, investigates the bug, answers two questions, posts the
result as a comment, then assigns and labels the issue. It is **read-only on
source** - any throwaway reproduction goes in a scratch directory outside the repo.

1. **Does the bug make sense?** - is the report consistent with the code?
2. **Can we reproduce it?** - attempt it and record the evidence.

When finished it also updates the issue itself:
- assigns it back to the issue author, and
- applies the label `issue-analysed` plus one outcome label (see step 7).

## Paths

- `SKILL_DIR` - this skill's base directory.
- `SKILLS_ROOT` - the parent of `SKILL_DIR` (contains `_review-lib/`).
- `TMP` - any scratch directory (e.g. `$env:TEMP` on Windows, `/tmp` elsewhere).

Commands below are single-line and shell-neutral: they run unchanged in POSIX
shells and Windows PowerShell.

## Prerequisites

- GitHub CLI installed and authenticated: run the `check` command below.
- For code tracing and reproduction, a **local checkout** of the repo (`--repo-root`).

## Workflow

### 1. Verify GitHub access

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" check
```

### 2. Fetch the issue

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" issue-fetch --repo <owner/repo> --issue <N> > "<TMP>/issue.json"
```

### 3. Extract structure and code hints

```bash
python "<SKILL_DIR>/scripts/issue_checks.py" extract --issue-json "<TMP>/issue.json" --repo-root "<path-to-checkout>" --json > "<TMP>/issue-extract.json"
```

The result contains parsed `sections` (steps, expected, actual, environment, logs),
`keywords`, and `code_hits` (files most likely involved).

### 4. Investigate

- Read the `code_hits` files and trace the code path. Cite `file:line`.
- Answer **Q1**: does the bug make sense? (`yes` / `no` / `unclear` + reasoning).
- Answer **Q2**: can we reproduce it? Run existing tests first, then a minimal
  script in `TMP` (never inside the repo). Record the exact command and output.
- Load the guidelines before deciding:
  `python "<SKILLS_ROOT>/_review-lib/cli.py" guidelines --skill debug-analysis --key debug --repo <owner/repo> --ref <default branch> --json`

### 5. Write the analysis

Create `<TMP>/analysis.json`:

```json
{
  "summary": "One-paragraph summary.",
  "confidence": "high|medium|low",
  "makes_sense": { "verdict": "yes|no|unclear", "reasoning": "Trace with file:line." },
  "reproducible": {
    "verdict": "yes|no|unknown",
    "method": "How reproduction was attempted.",
    "command": "exact command run",
    "evidence": "observed output"
  },
  "next_steps": ["suggested follow-ups"]
}
```

Never invent output - if it was not run, say so and use `unknown`.

### 6. Render and post the comment

```bash
python "<SKILL_DIR>/scripts/issue_checks.py" render --issue-json "<TMP>/issue.json" --analysis "<TMP>/analysis.json" --guidelines "general[,repo-specific]" --comment-out "<TMP>/debug-comment.md"
```

Post a **new** comment by default:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment --repo <owner/repo> --number <N> --kind issue --body-file "<TMP>/debug-comment.md"
```

Only when the user asks to update in place:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" find-comment --repo <owner/repo> --number <N> --marker "<!-- debug-analysis-agent -->"
```

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment-update --repo <owner/repo> --comment-id <id> --body-file "<TMP>/debug-comment.md"
```

### 7. Assign and label the issue

Assign the issue back to its **author** (from the fetched issue) and apply
`issue-analysed` plus exactly **one** outcome label you judge from the analysis:

| Outcome | Label | When |
| --- | --- | --- |
| Confirmed defect | `bug` | `makes_sense = yes` and the report describes broken behaviour |
| New capability | `enhancement` | The report asks for behaviour that never existed |
| Cannot be validated | `invalid` | `makes_sense = no` - the report contradicts the code |
| Not enough information | `needs-info` | `makes_sense = unclear` or reproduction needs more detail |
| Usage / how-to | `question` | Not a defect - the user needs guidance |

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" issue-edit --repo <owner/repo> --number <N> --assignee "<author-login>" --label issue-analysed --label <outcome> --ensure-labels
```

`--ensure-labels` creates any missing labels first, so the command does not fail
on a repo that has never seen `issue-analysed` before. The command is additive:
it never removes existing assignees or labels.

## Guardrails

- Never modify repository source, tests, or data - comment, assign, and label only.
- Only touch the issue's assignee and labels additively; never remove existing ones.
- Put reproduction scripts in a scratch directory outside the repo.
- Never fabricate evidence; state uncertainty honestly.
- Always append the marker `<!-- debug-analysis-agent -->` so comments are identifiable.
