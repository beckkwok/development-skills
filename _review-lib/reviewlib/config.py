"""Default review configuration and per-repo overrides.

A target repository may commit ``.review/config.json`` to extend or replace the
defaults below. Nothing here changes repository content — configuration is only
read to steer detection and tooling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import gh

DEFAULT_DB_GLOBS = [
    # Migration frameworks / directories
    "**/migrations/**",
    "**/migration/**",
    "**/migrate/**",
    "**/alembic/**",
    "db/migrate/**",
    "**/flyway/**",
    "**/liquibase/**",
    "**/*changelog*.xml",
    # SQL and schema artifacts
    "**/*.sql",
    "**/*.ddl",
    "**/V*__*.sql",
    "**/R__*.sql",
    "**/U*__*.sql",
    "**/schema.prisma",
    "**/schema.rb",
    "**/schema.sql",
    # ORM model surfaces
    "**/models/**",
    "**/entities/**",
    "**/*.entity.ts",
    "**/orm/**",
    "**/sequelize/**",
    "**/typeorm/**",
    "**/prisma/**",
]

DEFAULT_TEST_GLOBS = [
    "**/test/**",
    "**/tests/**",
    "**/spec/**",
    "**/specs/**",
    "**/__tests__/**",
    "**/test_*",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
]

DEFAULT_DOC_GLOBS = [
    "**/*.md",
    "**/*.rst",
    "**/*.adoc",
    "**/*.txt",
    "**/docs/**",
]

DEFAULT_CODE_EXTS = [
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".rb",
    ".go",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".php",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".swift",
    ".scala",
    ".sh",
    ".bash",
    ".ps1",
    ".dart",
    ".ex",
    ".exs",
    ".vue",
    ".svelte",
    ".lua",
    ".pl",
    ".r",
    ".m",
    ".mm",
]

DEFAULT_GUIDELINES = {
    "db": ".review/db-guidelines.md",
    "code": ".review/code-guidelines.md",
    "debug": ".review/debug-guidelines.md",
}

DEFAULTS: dict[str, Any] = {
    "db_globs": DEFAULT_DB_GLOBS,
    "test_globs": DEFAULT_TEST_GLOBS,
    "doc_globs": DEFAULT_DOC_GLOBS,
    "code_exts": DEFAULT_CODE_EXTS,
    "guidelines": dict(DEFAULT_GUIDELINES),
    "registry": "docs/db/schema-registry.md",
    "config_path": ".review/config.json",
    "commands": {"lint": None, "test": None},
    "require_rollback": True,
    "require_tests": True,
}


def deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge ``override`` into ``base`` (override wins)."""
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    result = dict(base)
    for key, value in override.items():
        result[key] = deep_merge(base.get(key), value) if key in base else value
    return result


def load_config_file(path: str | Path) -> dict[str, Any] | None:
    """Load a JSON config file, or ``None`` when it is absent/invalid."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def fetch_repo_config(repo: str, ref: str | None = None, path: str | None = None) -> dict[str, Any] | None:
    """Fetch ``.review/config.json`` from a remote repo, or ``None``."""
    path = path or DEFAULTS["config_path"]
    raw = gh.fetch_raw_file(repo, path, ref=ref)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def resolve(
    *,
    repo_root: str | None = None,
    repo: str | None = None,
    ref: str | None = None,
    explicit: dict[str, Any] | None = None,
    use_repo_config: bool = True,
) -> dict[str, Any]:
    """Resolve the effective config: defaults <- repo config <- explicit overrides."""
    cfg = DEFAULTS
    repo_cfg: dict[str, Any] | None = None
    if use_repo_config:
        if repo_root:
            repo_cfg = load_config_file(Path(repo_root) / DEFAULTS["config_path"])
        elif repo:
            repo_cfg = fetch_repo_config(repo, ref=ref)
    if repo_cfg:
        cfg = deep_merge(cfg, repo_cfg)
    if explicit:
        cfg = deep_merge(cfg, explicit)
    return cfg
