# General QA verification guidelines

Applies to every repository. Repo-specific guidelines (`.review/qa-guidelines.md`)
extend these rules and always take precedence.

## Independence

- The QA run needs only **repo + issue** (plus an optional explicit PR/branch/ref).
- Never depend on the coding agent's session, machine, or uncommitted state.
- Self-clone or use a clean checkout at the exact ref under test; record it.

## Acceptance criteria

- Derive criteria from the issue: task lists first, then acceptance/expected sections.
- Every criterion ends the run as **verified**, **failed**, or **unverified**.
- A criterion is verified only with cited evidence (a recorded step, output, or screenshot).

## Evidence rules

- Record every step uniformly: exact command, exit code, duration, output excerpt.
- Prefer real output over summaries. Never fabricate logs, output, or screenshots.
- Screenshots must show the actual behavior under test, with a caption saying what
  each one proves. Hosted URLs are embedded; local paths are listed for manual upload.
- State confidence as **high**, **medium**, or **low**.

## Verdicts

- **QA PASS** — every criterion verified and every executed step green.
- **QA FAIL** — any criterion failed or any step non-zero.
- **QA INCONCLUSIVE** — anything unverified or nothing executed; say what is missing.

## Safety

- Running tests is the only execution allowed. Do not modify source, tests, or data.
- Put throwaway probes and proof artifacts outside the repo.
- Do not push, commit, or open PRs as part of verification.
