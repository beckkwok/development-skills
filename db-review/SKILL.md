---
name: db-review
description: Review a GitHub pull request for database/schema changes (SQL, migrations, ORM models, schema files), post a DB review comment, and update the schema registry. Use when asked to "DB review", "review database changes", "vet a migration PR", or check a PR for SQL/migration/schema risk.
---

# DB Review Skill

Vets a GitHub PR for database changes, posts a review comment, and records the
change in the repository's schema registry. It **never touches data, source, or
migrations** - it only reads, comments, and (on PASS) updates the registry doc.

## Paths

- `SKILL_DIR` - this skill's base directory.
- `SKILLS_ROOT` - the parent of `SKILL_DIR` (contains `_review-lib/`).
- `TMP` - any scratch directory (e.g. `$env:TEMP` on Windows, `/tmp` elsewhere).

Commands below are single-line and shell-neutral: they run unchanged in POSIX
shells and Windows PowerShell.

## Prerequisites

- GitHub CLI installed and authenticated: run the `check` command below.
- For registry updates, a **local checkout** of the target repo passed as `--repo-root`.

## Workflow

### 1. Verify GitHub access

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" check
```

### 2. Fetch the PR

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" pr-fetch --repo <owner/repo> --pr <N> > "<TMP>/pr.json"
```

`pr.json` contains `meta` (title, url, author, `headRefOid`), `files` (with patches)
and `diff`. Readers accept UTF-8 and UTF-16 output files.

### 3. Load guidelines

Read both layers and apply them together:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" guidelines --skill db-review --key db --repo <owner/repo> --ref <headRefOid> --json
```

- Add `--repo-root <path>` instead of `--repo/--ref` when working from a checkout.
- `sources` tells you which layers exist (`general`, `repo-specific`). Pass those
  names to `--guidelines` so the comment records what was applied.

### 4. Analyze

```bash
python "<SKILL_DIR>/scripts/db_checks.py" --pr-json "<TMP>/pr.json" --comment-out "<TMP>/db-comment.md" --summary "<one-line summary>" --guidelines "general[,repo-specific]" --repo-root "<path-to-checkout>" --json > "<TMP>/db-result.json"
```

The result JSON has `verdict`, `findings`, `db_files`, `migration_scripts`,
`rollback_scripts`, `schema_changes` and `registry_entry`.

- **No `db_files`:** post a short PASS comment stating no DB changes were found and stop
  (do not update the registry).
- Otherwise continue.

### 5. Post the review comment

Post a **new** comment by default:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment --repo <owner/repo> --number <N> --kind pr --body-file "<TMP>/db-comment.md"
```

Only when the user asks to update in place:

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" find-comment --repo <owner/repo> --number <N> --marker "<!-- db-review-agent -->"
```

```bash
python "<SKILLS_ROOT>/_review-lib/cli.py" comment-update --repo <owner/repo> --comment-id <id> --body-file "<TMP>/db-comment.md"
```

### 6. Update the schema registry (PASS only)

With a local checkout:

```bash
python "<SKILL_DIR>/scripts/db_checks.py" --pr-json "<TMP>/pr.json" --repo-root "<path-to-checkout>" --update-registry --json
```

- Default registry path: `docs/db/schema-registry.md` (override with `--registry`
  or `.review/config.json`).
- Without a local checkout, print the entry (`--entry-only`) and include it in the
  comment so a maintainer can apply it. Do **not** attempt to push.

## Verdict policy

| Verdict | Meaning | Action |
| --- | --- | --- |
| `pass` | No blockers/errors/warnings | Comment PASS; update registry. |
| `warn` | Only warnings | Comment "PASS WITH WARNINGS"; registry update allowed. |
| `fail` | Any blocker | Comment **FAILED** with itemized findings; registry unchanged. |

A **missing rollback script is a blocker** - the comment is posted marked FAILED and
the author is told to add one. Never generate the rollback script.

## Guardrails

- Never modify source code, business logic, migrations, or data.
- Never generate migration or rollback scripts - flag them instead.
- Update the registry document only on PASS and only in a local checkout.
- If unsure, report a finding rather than taking a write action.
- Always append the marker `<!-- db-review-agent -->` so comments are identifiable.
