from __future__ import annotations

from pathlib import Path


def load_template(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def render_template(template: str, context: dict[str, str]) -> str:
    return template.format(**context)
