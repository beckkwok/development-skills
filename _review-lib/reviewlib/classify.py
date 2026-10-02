"""Classify changed files into review categories.

Conservative by design: a file is only treated as a DB change when it matches a
known migration/schema/ORM pattern. Classification never writes anything.
"""

from __future__ import annotations

import fnmatch
import posixpath
from typing import Any, Iterable

from .config import (
    DEFAULT_CODE_EXTS,
    DEFAULT_DB_GLOBS,
    DEFAULT_DOC_GLOBS,
    DEFAULT_TEST_GLOBS,
)

CATEGORIES = ("db", "test", "doc", "code", "other")


def path_of(entry: Any) -> str:
    """Extract a file path from a diff entry (str or dict)."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("filename") or entry.get("path") or ""
    return ""


def _norm(path: str) -> str:
    normalized = posixpath.normpath(str(path).replace("\\", "/"))
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches(path: str, globs: Iterable[str]) -> bool:
    normalized = _norm(path)
    prefixed = "/" + normalized
    return any(
        fnmatch.fnmatch(normalized, glob) or fnmatch.fnmatch(prefixed, glob)
        for glob in globs
    )


def classify_path(
    path: str,
    *,
    db_globs: Iterable[str] | None = None,
    test_globs: Iterable[str] | None = None,
    doc_globs: Iterable[str] | None = None,
    code_exts: Iterable[str] | None = None,
) -> str:
    """Return one of ``db``/``test``/``doc``/``code``/``other`` for a path."""
    db_globs = db_globs if db_globs is not None else DEFAULT_DB_GLOBS
    test_globs = test_globs if test_globs is not None else DEFAULT_TEST_GLOBS
    doc_globs = doc_globs if doc_globs is not None else DEFAULT_DOC_GLOBS
    code_exts = code_exts if code_exts is not None else DEFAULT_CODE_EXTS

    if _matches(path, test_globs):
        return "test"
    if _matches(path, db_globs):
        return "db"
    if _matches(path, doc_globs):
        return "doc"
    ext = posixpath.splitext(_norm(path))[1].lower()
    if ext in set(code_exts):
        return "code"
    return "other"


def classify_files(files: Iterable[Any], config: dict[str, Any] | None = None) -> dict[str, list[Any]]:
    """Group diff entries by category using the effective config."""
    config = config or {}
    db_globs = config.get("db_globs") or DEFAULT_DB_GLOBS
    test_globs = config.get("test_globs") or DEFAULT_TEST_GLOBS
    doc_globs = config.get("doc_globs") or DEFAULT_DOC_GLOBS
    code_exts = config.get("code_exts") or DEFAULT_CODE_EXTS

    grouped: dict[str, list[Any]] = {name: [] for name in CATEGORIES}
    for entry in files:
        category = classify_path(
            path_of(entry),
            db_globs=db_globs,
            test_globs=test_globs,
            doc_globs=doc_globs,
            code_exts=code_exts,
        )
        grouped[category].append(entry)
    return grouped


def db_files(files: Iterable[Any], config: dict[str, Any] | None = None) -> list[Any]:
    """Return only the entries classified as DB-relevant."""
    return classify_files(files, config)["db"]
