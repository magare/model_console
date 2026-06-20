"""Logging and file-system helpers.

Provides UTC timestamp generation, directory creation, JSON/JSONL writing,
and dataclass-to-dict serialisation with automatic secret redaction.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..safety import redact_text

__all__ = [
    "utc_now_iso",
    "ensure_dir",
    "to_jsonable",
    "write_json",
    "append_jsonl",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def to_jsonable(value: Any, _visited: set[int] | None = None) -> Any:
    """Convert a value to a JSON-serializable form with cycle detection.

    Handles dataclasses, Paths, dicts, lists, and provides a fallback for
    non-serializable types. Cycle detection prevents infinite recursion on
    circular references.
    """
    if _visited is None:
        _visited = set()

    # Use object identity for cycle detection
    value_id = id(value)
    if value_id in _visited:
        return "[Circular Reference]"
    _visited.add(value_id)

    try:
        if is_dataclass(value):
            return to_jsonable(asdict(value), _visited)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): to_jsonable(v, _visited) for k, v in value.items()}
        if isinstance(value, list):
            return [to_jsonable(v, _visited) for v in value]
        if isinstance(value, (str, int, float, bool, type(None))):
            return value

        # Fallback: convert non-serializable types to string representation
        return str(value)
    finally:
        # Clean up visited set for parent calls
        _visited.discard(value_id)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    try:
        jsonable = to_jsonable(payload)
        # Verify the output is actually JSON-serializable before writing
        json.dumps(jsonable)  # Test serialization
        with path.open("w", encoding="utf-8") as f:
            json.dump(jsonable, f, indent=2, sort_keys=True)
    except (TypeError, ValueError) as exc:
        # If serialization still fails, provide a meaningful error
        raise TypeError(
            f"Cannot serialize payload to JSON: {exc}. "
            f"Payload type: {type(payload).__name__}"
        ) from exc


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)

    def redact_value(value: Any, _visited: set[int] | None = None) -> Any:
        """Recursively redact secrets in values."""
        if _visited is None:
            _visited = set()

        # Handle primitive types
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, (int, float, bool, type(None))):
            return value

        # Handle collections - recurse with cycle detection
        value_id = id(value)
        if value_id in _visited:
            return "[Circular Reference]"
        _visited.add(value_id)

        try:
            if isinstance(value, dict):
                return {k: redact_value(v, _visited) for k, v in value.items()}
            if isinstance(value, list):
                return [redact_value(v, _visited) for v in value]
            # For other types, convert to string and redact
            return redact_text(str(value))
        finally:
            _visited.discard(value_id)

    safe_payload = redact_value(to_jsonable(payload))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe_payload, sort_keys=True) + "\n")
