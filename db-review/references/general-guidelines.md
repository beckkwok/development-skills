# General DB review guidelines

Applies to every repository. Repo-specific guidelines (`.review/db-guidelines.md`)
extend these rules and always take precedence.

## What counts as a DB change

- Migration files: `migrations/`, `migrate/`, `alembic/`, `db/migrate/`, Flyway
  `V*__*.sql`, Liquibase changelogs, goose.
- Schema definitions: `schema.prisma`, `schema.rb`, `*.sql`, `*.ddl`.
- ORM models: `models/`, `entities/`, `*.entity.ts`, TypeORM/Sequelize/Prisma.

## Blockers (fail the review)

1. **Destructive DDL without a plan** - `DROP TABLE/COLUMN/DATABASE`, `TRUNCATE`,
   `DELETE FROM` without `WHERE`.
2. **Missing rollback** - every migration must have a down/undo path
   (sibling `.down.sql`/`.rollback.sql`, Flyway `U*__*.sql`, Alembic `downgrade()`,
   Rails `down`/`reversible`, goose `-- +migrate Down`). Missing rollback = FAILED.
   Set `"require_rollback": false` in `.review/config.json` only for intentionally
   forward-only pipelines.
3. **`NOT NULL` added without `DEFAULT`** on a non-empty table.
4. **Secret/credential literals** committed in SQL.

## Warnings (review, may not block)

- `ALTER COLUMN ... TYPE` / `MODIFY COLUMN` - table rewrite + lock.
- `SET NOT NULL` - full scan under `ACCESS EXCLUSIVE`.
- `CREATE INDEX` without `CONCURRENTLY` - blocks writes.
- `RENAME COLUMN/TABLE` - breaks existing code.
- `ON DELETE CASCADE` - silent related-row deletion.
- `ADD COLUMN ... DEFAULT` on large tables (rewrite on older engines).

## Always check

- Migration ordering / duplicate version prefixes.
- Foreign keys have a supporting index.
- Migrations are idempotent (`IF NOT EXISTS`) where re-run is possible.
- No business-logic changes bundled into a migration PR.

## Reporting

- One finding per issue with `file:line` and the rule id.
- Missing rollback is reported explicitly and marks the review **FAILED**.
- Never generate migrations or rollback scripts - only flag them.
