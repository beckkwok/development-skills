---
name: debug-analysis
description: Analyze a GitHub issue - bugs and feature requests - then post the analysis as a comment, assign it back to the author, label it, and split large work into sub-issues. Use when asked to "analyze this bug", "debug analysis", "triage this issue", "can we reproduce this", "assess this feature request", or to investigate a GitHub issue.
---

# Debug Analysis Skill

Reads a GitHub issue, investigates it, and posts the result as a comment. It handles
two modes, detected from labels first and keywords second (`kind` in the extract output):

- **Bug mode** - answers two questions and posts the result:
  1. **Does the bug make sense?** - is the report consistent with the code?
  2. **Can we reproduce it?** - attempt it and record the evidence.
- **Feature mode** (feature requests, enhancements, questions) - assesses the request:
  restate it, judge feasibility against the codebase, state confidence, ask the author
  questions when unsure, and split large work into sub-issues.

When finished it also updates the issue itself:
- assigns it back to the issue author, and
- applies the label `issue-analysed` plus one outcome label (see step 8).

It is **read-only on repository files** - it never implements anything or modifies
source. The only writes are comments, issue assign/label, and new sub-issues.

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

### 3. Extract structure, kind, and code hints

```bash
python "<SKILL_DIR>/scripts/issue_checks.py" extract --issue-json "<TMP>/issue.json" --repo-root "<path-to-checkout>" --json > "<TMP>/issue-extract.json"
```

The result contains `kind` (`bug` | `feature` | `question` | `unclear`), parsed
`sections` (steps, expected, actual, environment, logs), `keywords`, and `code_hits`
(files most likely involved).

### 4. Investigate

- Read the `code_hits` files and trace the relevant code. Cite `file:line`.
- **Bug mode:** answer **Q1** (`yes` / `no` / `unclear` + reasoning) and **Q2**
  (run existing tests first, then a minimal script in `TMP`, never inside the repo;
  record the exact command and output).
- **Feature mode:** restate the request in your own words; check feasibility against
  the codebase (where would it plug in? what storage/API/UI changes?); set confidence
  (`high` / `medium` / `low`). If anything is unclear, write down questions for the author.
- Load the guidelines before deciding:
  `python "<SKILLS_ROOT>/_review-lib/cli.py" guidelines --skill debug-analysis --key debug --repo <owner/repo> --ref <default branch> --json`

### 5. Write the analysis

Create `<TMP>/analysis.json`. Bug mode:

```json
{
  "kind": "bug",
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

Feature/question mode:

```json
{
  "kind": "feature",
  "summary": "One-paragraph summary.",
  "confidence": "high|medium|low",
  "assessment": "Restated scope and how it fits the codebase, with file:line refs.",
  "feasibility": "Where it plugs in; blockers or unknowns.",
  "questions": ["Question 1 for the author?", "Question 2?"],
  "sub_issues": [{ "number": 12, "url": "https://...", "title": "[Parent #N] slice" }],
  "next_steps": ["suggested follow-ups"]
}
```

Never invent output - if it was not run, say so and use `unknown`. If confidence is
not high, `questions` must not be empty.

### 6. Split large work into sub-issues (only when needed)

Split when the work spans more than three distinct areas, touches many subsystems,
or is too big for one PR. Each slice gets its own issue via:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" issue-create --repo <owner/repo> --title "[Parent #<N>] <slice>" --body-file "<TMP>/sub-<k>.md" --label enhancement
```

Each sub-issue body states its scope, acceptance criteria, and a link back to the
parent (`Part of #<N>`). Record the created `{number, url, title}` objects in
`analysis.json` under `sub_issues`.

### 7. Render and post the comment

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

### 8. Assign and label the issue

Assign the issue back to its **author** (from the fetched issue) and apply
`issue-analysed` plus exactly **one** outcome label you judge from the analysis:

| Outcome | Label | When |
| --- | --- | --- |
| Confirmed defect | `bug` | `makes_sense = yes` and the report describes broken behaviour |
| New capability | `enhancement` | The report asks for behaviour that never existed |
| Cannot be validated | `invalid` | `makes_sense = no` - the report contradicts the code |
| Not enough information | `needs-info` | `makes_sense = unclear`, low confidence, or questions were asked |
| Usage / how-to | `question` | Not a defect - the user needs guidance |

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" issue-edit --repo <owner/repo> --number <N> --assignee "<author-login>" --label issue-analysed --label <outcome> --ensure-labels
```

`--ensure-labels` creates any missing labels first, so the command does not fail
on a repo that has never seen `issue-analysed` before. The command is additive:
it never removes existing assignees or labels.

## Guardrails

- Never modify repository source, tests, or data - comment, assign, label, and
  create sub-issues only. Never implement the requested feature or fix.
- Only touch the issue's assignee and labels additively; never remove existing ones.
- Put reproduction scripts in a scratch directory outside the repo.
- Never fabricate evidence; state uncertainty honestly and ask questions instead.
- Always append the marker `<!-- debug-analysis-agent -->` so comments are identifiable.
