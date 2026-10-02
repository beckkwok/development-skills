# DB Schema Registry

Catalogue of database schema changes reviewed by the `db-review` agent.
Each passing PR appends one entry, delimited by HTML markers so re-runs update
in place instead of duplicating.

<!-- db-registry:start PR#123 -->
### PR #123: Add users.email index

- **Repo:** owner/repo
- **PR:** https://github.com/owner/repo/pull/123
- **Author:** octocat
- **Reviewed:** 2026-01-01
- **Status:** PASS

**DB files**
- `db/migrate/20260101_add_email_index.sql`

**Schema changes**
- create index `idx_users_email` (`db/migrate/20260101_add_email_index.sql`)

**Migration scripts**
- `db/migrate/20260101_add_email_index.sql`

**Rollback scripts**
- `db/migrate/20260101_add_email_index.down.sql`

**Risk notes**
- _(none)_
<!-- db-registry:end PR#123 -->
