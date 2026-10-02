# General code review guidelines

Applies to every repository. Repo-specific guidelines (`.review/code-guidelines.md`)
extend these rules and always take precedence.

## Blockers (fail the review)

1. **Unresolved merge conflict markers** (`<<<<<<<`, `=======`, `>>>>>>>`).
2. **Committed secrets** - private keys, cloud access keys, API tokens, hardcoded
   credentials. Placeholders such as `changeme`/`example` are ignored.

## Errors (PASS WITH WARNINGS, must be addressed)

1. **Missing tests** - source changed with no test added or updated
   (disable with `"require_tests": false` for docs/config-only repos).
2. **Swallowed exceptions** - bare `except: pass` or empty `catch {}`.
3. **Configured lint/test command failed** (when run).

## Warnings

- Debugging statements left in (`console.log`, `debugger`, `binding.pry`, `pdb`).
- `eval`/`exec` usage.
- `TODO`/`FIXME`/`HACK`/`XXX` markers added.

## Notes

- Print-style output (`print`, `println`, `fmt.Print`) - informational, often legitimate.

## Always check

- The change matches the PR description and stays in scope.
- New code follows existing patterns, naming and structure.
- Error handling is present and meaningful on I/O and network paths.
- Public APIs and behaviour changes are documented where the repo expects it.
- No dead or commented-out code is left behind.

## Reporting

- One finding per issue with `file:line` and the rule id.
- Never modify code; only comment. Missing tests is reported explicitly.
