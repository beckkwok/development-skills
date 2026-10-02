# General debug analysis guidelines

Applies to every repository. Repo-specific guidelines (`.review/debug-guidelines.md`)
extend these rules and always take precedence.

## Question 1 - Does the bug make sense?

- Restate the reported behaviour in your own words.
- Trace the relevant code path; cite `file:line`.
- Decide: **Yes** (the report is consistent with the code), **No** (the code cannot
  behave that way), or **Unclear** (needs more information).
- Call out missing information (version, platform, input, config).

## Question 2 - Can we reproduce it?

- Attempt reproduction with existing tests first, then a minimal standalone script.
- Record the exact command and the observed output as evidence.
- Decide: **Yes**, **No**, or **Unknown** (could not set up the environment).
- If not reproducible, say what was tried and what is needed to try.

## Evidence rules

- Prefer real output over speculation. Quote the smallest relevant snippet.
- Never fabricate logs, stack traces, or command output.
- State confidence as **high**, **medium**, or **low**.

## Safety

- Do not modify repository source or tests. Put throwaway repro scripts in a
  scratch directory outside the repo.
- Do not push, commit, or open PRs.
