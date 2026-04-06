"""JSON schema validator.

Uses jsonschema (Draft 2020-12) when available; otherwise falls back to a
lightweight built-in checker that validates types, required fields, enums,
const, minLength, and numeric bounds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator  # type: ignore
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment]


def validate_with_schema(schema_path: Path, payload: dict[str, Any]) -> list[str]:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    if Draft202012Validator is not None:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
        return [e.message for e in errors]
    return _validate_fallback(schema, payload, "$")


def _validate_fallback(schema: dict[str, Any], value: Any, path: str) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")

    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property missing")

        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key in value:
                errors.extend(
                    _validate_fallback(child, value[key], f"{path}.{key}")
                )

        if schema.get("additionalProperties") is False:
            allowed = set(properties.keys())
            for key in value.keys():
                if key not in allowed:
                    errors.append(f"{path}.{key}: additional property not allowed")

    elif expected_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(_validate_fallback(item_schema, item, f"{path}[{idx}]"))

    elif expected_type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
        enum_vals = schema.get("enum")
        if enum_vals is not None and value not in enum_vals:
            errors.append(f"{path}: value `{value}` not in enum")
        const_val = schema.get("const")
        if const_val is not None and value != const_val:
            errors.append(f"{path}: value `{value}` does not match const `{const_val}`")
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and isinstance(value, str) and len(value) < min_len:
            errors.append(f"{path}: length must be >= {min_len}")

    elif expected_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path}: expected number")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: must be >= {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: must be <= {maximum}")

    if expected_type is None:
        enum_vals = schema.get("enum")
        if enum_vals is not None and value not in enum_vals:
            errors.append(f"{path}: value `{value}` not in enum")

        const_val = schema.get("const")
        if const_val is not None and value != const_val:
            errors.append(f"{path}: value `{value}` does not match const `{const_val}`")

    return errors
