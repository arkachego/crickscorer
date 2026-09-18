"""In-memory per-match snapshot version (no DB schema change)."""

from __future__ import annotations

import threading
import uuid

_lock = threading.Lock()
_versions: dict[str, int] = {}


def bump_match_version(match_id: uuid.UUID) -> int:
    """Increment and return the next monotonic version for a match."""
    key = str(match_id)
    with _lock:
        current = _versions.get(key, 0) + 1
        _versions[key] = current
        return current


def current_match_version(match_id: uuid.UUID) -> int:
    with _lock:
        return _versions.get(str(match_id), 0)


def reset_versions_for_tests() -> None:
    """Test helper — clear in-memory versions between cases."""
    with _lock:
        _versions.clear()
