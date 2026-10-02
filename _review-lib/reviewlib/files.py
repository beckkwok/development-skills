"""Encoding-tolerant text file reading.

POSIX shells write captured output as UTF-8, while Windows PowerShell 5.1
redirection (``>``) writes UTF-16. Readers try UTF-8 (with or without BOM)
first, then UTF-16, so ``> file`` output works on both without the caller
caring. Files written by these tools are always plain UTF-8.
"""

from __future__ import annotations

from pathlib import Path

_ENCODINGS = ("utf-8-sig", "utf-16")


def read_text(path: str | Path) -> str:
    """Read a text file, tolerating UTF-8, UTF-8-BOM, and UTF-16."""
    data = Path(path).read_bytes()
    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")
