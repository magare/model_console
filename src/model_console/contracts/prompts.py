"""Prompt template helpers.

Loads plain-text template files and renders them via str.format() substitution
to build the prompts sent to implementer and reviewer agents.
"""

from __future__ import annotations

from pathlib import Path
from string import Formatter
from typing import Any


def load_template(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def render_template(template: str, context: dict[str, Any]) -> str:
    """Render a template using str.format() substitution.

    Args:
        template: The template string with {key} placeholders
        context: Dictionary of values to substitute

    Returns:
        The rendered template string

    Raises:
        KeyError: If a placeholder in the template is not provided in context
    """
    # Validate that all template placeholders are in context before rendering
    # This provides a clearer error message than str.format's default
    formatter = Formatter()
    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        if field_name is not None and field_name not in context:
            raise KeyError(
                f"Template placeholder '{{{field_name}}}' not found in provided context. "
                f"Available keys: {sorted(context.keys())}"
            )
    return template.format(**context)
