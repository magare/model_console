"""Small validation helpers shared across config and API parsing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    # Convert Mapping to dict for consistent return type
    # Use dict() constructor which accepts any Mapping
    return dict(value)


def require_string_field(
    payload: Mapping[str, Any],
    key: str,
    label: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{label} missing required field `{key}`")
    if not isinstance(value, str):
        raise ValueError(f"{label} field `{key}` must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{label} field `{key}` cannot be empty or whitespace only")
    return value
