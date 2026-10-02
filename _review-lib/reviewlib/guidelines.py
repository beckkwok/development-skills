"""Load and merge general (shipped) and repo-specific review guidelines.

General guidelines live beside each skill in ``references/general-guidelines.md``.
Repo-specific guidelines are optional and live inside the target repository
(default ``.review/<skill>-guidelines.md``). Repo rules extend the general ones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from . import config as config_mod
from . import files
from . import gh

GENERAL_FILENAME = "general-guidelines.md"


def load_general(skill_dir: str | Path) -> str:
    """Read the general guideline shipped with a skill, if present."""
    path = Path(skill_dir) / "references" / GENERAL_FILENAME
    if not path.is_file():
        return ""
    return files.read_text(path)


def load_repo_guideline(
    *,
    repo_root: str | None = None,
    repo: str | None = None,
    ref: str | None = None,
    path: str = ".review/db-guidelines.md",
) -> str:
    """Read a repo-specific guideline from a local checkout or the GitHub API."""
    if repo_root:
        p = Path(repo_root) / path
        return files.read_text(p) if p.is_file() else ""
    if repo:
        return gh.fetch_raw_file(repo, path, ref=ref) or ""
    return ""


def load_merged(
    *,
    skill_dir: str | Path,
    key: str = "db",
    repo_root: str | None = None,
    repo: str | None = None,
    ref: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return general + repo-specific guidelines and a merged document."""
    cfg = cfg or config_mod.DEFAULTS
    relative = (cfg.get("guidelines") or {}).get(key) or f".review/{key}-guidelines.md"
    general = load_general(skill_dir)
    repo_specific = load_repo_guideline(repo_root=repo_root, repo=repo, ref=ref, path=relative)

    sources = ["general"]
    combined = general
    if repo_specific.strip():
        sources.append("repo-specific")
        combined = (
            f"{general}\n\n---\n\n"
            f"# Repo-specific guidelines (`{relative}`)\n\n{repo_specific}"
        )

    return {
        "key": key,
        "path": relative,
        "general": general,
        "repo": repo_specific,
        "sources": sources,
        "combined": combined,
    }
