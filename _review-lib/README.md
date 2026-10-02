# `_review-lib` — shared helpers for review skills

Dependency-free (standard library only) helpers shared by `db-review`, `code-review`,
`debug-analysis` and `branch-pr`. It has **no `SKILL.md`**, so agents never load it
as a skill — they call it as a command.

## Requirements

- Python 3.9+
- [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`)

## Layout

```
_review-lib/
  cli.py               # command entrypoint (run this)
  reviewlib/
    gh.py              # fetch PR/issue, post/update comments, issue-edit, pr-create
    classify.py        # path -> db / test / doc / code / other
    config.py          # defaults + .review/config.json overrides
    files.py           # encoding-tolerant file reading (UTF-8 / UTF-16)
    guidelines.py      # merge general + repo-specific guidelines
    render.py          # findings JSON -> Markdown comment
  tests/               # offline unit tests
```

## Commands

Run from a skill via a path relative to the skills root:

```bash
python <skills-root>/_review-lib/cli.py <command> [options]
```

| Command | Purpose |
| --- | --- |
| `check` | Verify `gh` is installed and authenticated. |
| `pr-fetch --repo owner/repo --pr N [--no-diff]` | PR metadata, files (with patches) and diff as JSON. |
| `issue-fetch --repo owner/repo --issue N` | Issue with comments as JSON. |
| `classify --repo owner/repo --pr N` | Group changed files into categories. |
| `guidelines --skill db-review [--repo --ref] [--json]` | Merged general + repo-specific guidelines. |
| `comment --repo owner/repo --number N [--kind pr\|issue] --body-file -` | Post a new comment. |
| `comment-update --repo owner/repo --comment-id ID --body-file -` | Edit a comment in place. |
| `find-comment --repo owner/repo --number N --marker TEXT` | Find a comment by marker. |
| `issue-edit --repo owner/repo --number N [--assignee L] [--label L] [--ensure-labels]` | Add assignees/labels (additive only). |
| `render --skill "DB Review" --verdict pass\|fail --findings -` | Render a Markdown comment body. |

Common options: `--config-file`, `--repo-root`, `--no-repo-config`.

## Comment policy

- **Post a new comment by default.**
- Update in place only when explicitly requested: `find-comment` → `comment-update`.

## Guidelines

`guidelines` merges two layers:

1. **General** — `references/general-guidelines.md` inside each skill (all repos).
2. **Repo-specific** — `.review/<key>-guidelines.md` inside the target repo (optional).

Repo rules extend the general ones. Both are reported in the comment so the author
knows what was applied.

## Per-repo config (`.review/config.json`)

Optional; deep-merged over defaults. Example:

```json
{
  "db_globs": ["db/migrate/**", "**/*.sql"],
  "guidelines": { "db": ".review/db-guidelines.md" },
  "registry": "docs/db/schema-registry.md",
  "commands": { "lint": "npm run lint", "test": "npm test" }
}
```

## Windows / PowerShell notes

Skill examples are single-line and shell-neutral, but keep these differences in mind:

- PowerShell 5.1 has no `\` line continuation. Run each example command on one line.
- PowerShell `>` redirection writes **UTF-16**. All readers here accept UTF-8
  (with or without BOM) and UTF-16, and everything written is plain UTF-8 — so
  capturing output with `>` works on both shells.
- Quoting differs: PowerShell uses the backtick for escapes and `;` separates
  statements. Prefer probe/script **files** over inline quoted code, e.g.
  `python /tmp/probe.py` instead of `python -c "..."`.

## Safety

These helpers are **read-only on source**. They post comments and read files; they
never modify code, migrations, or data.

## Tests

```bash
python -m unittest discover -s tests -t .
```
