---
name: qa-verify
description: Verify completed coding work against a GitHub issue and post the QA result as an issue comment with step-by-step proof. Use when asked to "QA this", "verify the fix", "test the coding result", "quality assurance", "acceptance test", or to check that an issue is resolved.
---

# QA Verify Skill

Tests completed coding work against a GitHub issue and posts the QA result as an
issue comment with step-by-step proof. It is **independent** — it needs only the
repo and issue, so it can run on a different machine or model than the coding agent.

## Paths

- `SKILL_DIR` - this skill's base directory.
- `SKILLS_ROOT` - the parent of `SKILL_DIR` (contains `_review-lib/`).
- `TMP` - any scratch directory (e.g. `$env:TEMP` on Windows, `/tmp` elsewhere).

## Prerequisites

- GitHub CLI installed and authenticated: run the `check` command below.
- A local checkout of the repo at the exact ref under test (`--repo-root`), or a
  directory to clone into.

## Workflow

### 1. Verify GitHub access

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" check
```

### 2. Fetch the issue

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" issue-fetch --repo <owner/repo> --issue <N> > "<TMP>/issue.json"
```

### 3. Resolve criteria and target

```bash
python "<SKILL_DIR>/scripts/qa_checks.py" resolve --repo <owner/repo> --issue <N> \
  --repo-root "<path-to-checkout>"
```

- Extracts acceptance criteria from the issue (task lists, then acceptance sections).
- Finds the linked PR via the issue timeline (override with `--pr`, `--branch`, or `--ref`).
- Suggests test commands from `.review/config.json` or stack markers
  (`flutter test`, `npm test`, `pytest`, `go test ./...`, ...).
- Without network access, pass `--issue-json "<TMP>/issue.json"` instead of `--repo/--issue`.
- Check out the resolved ref in a **clean** checkout before testing.

### 4. Run verification, recording every step

```bash
python "<SKILL_DIR>/scripts/qa_checks.py" run --repo-root "<path-to-checkout>" \
  --step "<name>" --out "<TMP>/results.json>" -- "<command>"
```

- Run the test suite first, then one acceptance probe per criterion.
- Each run appends `{step, command, exit_code, duration_s, output}` to the results file.
- Probes and proof artifacts live in `TMP`, never inside the repo.

### 5. Judge each criterion and render the report

Write the criteria verdicts into `<TMP>/results.json`:

```json
{
  "target": { "pr": 59, "branch": "feature/2-user-feedback", "ref": "<sha>" },
  "environment": "Windows 11, Flutter 3.44.4",
  "summary": "One-paragraph summary.",
  "criteria": [
    { "id": "C1", "text": "...", "verdict": "verified|failed|unverified", "support": "step 2" }
  ],
  "screenshots": [ { "caption": "what this proves", "url": "https://..." } ],
  "steps": [ ... ]
}
```

```bash
python "<SKILL_DIR>/scripts/qa_checks.py" render --issue-json "<TMP>/issue.json" \
  --results "<TMP>/results.json" --guidelines "general[,repo-specific]" \
  --comment-out "<TMP>/qa-comment.md"
```

- Verdict is computed: all verified + all green → **QA PASS**; any failure → **QA FAIL**;
  anything unverified → **QA INCONCLUSIVE** (override with `--verdict` if you must,
  and say why).

### 6. Post the QA report

Post a **new** comment by default:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment --repo <owner/repo> --number <N> \
  --kind issue --body-file "<TMP>/qa-comment.md"
```

Only when the user asks to update in place, use `find-comment` with the marker
`<!-- qa-verify-agent -->` followed by `comment-update`.

## Screenshots

- Capture real screenshots of the behavior under test (UI tests, browser runs)
  into `TMP`, with a caption stating what each proves.
- If the image is hosted (CI artifact, committed file), put its URL in
  `screenshots[].url` and it is embedded in the report.
- Otherwise list the local path; the report marks it for manual upload.
- Never fabricate, mock up, or reuse unrelated screenshots.

## Guardrails

- Running tests and probes is the only execution allowed - never modify
  repository source, tests, or data.
- Never fabricate evidence; `unverified`/`inconclusive` is always preferable to guessing.
- Always append the marker `<!-- qa-verify-agent -->` so reports are identifiable.
