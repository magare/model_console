"""Safety guardrails.

assert_command_safe() enforces allow/deny command policies before any
subprocess is executed.  redact_text() scrubs secrets (API keys, tokens,
passwords) from strings before they are persisted to logs.
"""

from __future__ import annotations

import re
import shlex

from .models import Policies


_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key\s*[=:]\s*)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(password\s*[=:]\s*)([^\s]{4,})", re.IGNORECASE),
]


def assert_command_safe(command: list[str], policies: Policies) -> None:
    joined = " ".join(command)
    for pattern in policies.deny_command_patterns:
        if re.search(pattern, joined):
            raise RuntimeError(f"Blocked by deny pattern `{pattern}`: {joined}")

    if policies.allow_command_prefixes:
        prefix = command[0] if command else ""
        if prefix not in policies.allow_command_prefixes:
            raise RuntimeError(
                f"Command `{prefix}` not allowlisted. Allowed: {policies.allow_command_prefixes}"
            )
        if prefix in {"zsh", "bash", "sh"} and len(command) >= 3 and command[1] in {"-lc", "-c"}:
            try:
                inner = shlex.split(command[2])
            except ValueError as exc:
                raise RuntimeError(f"Invalid shell command expression: {command[2]}") from exc
            if inner:
                inner_prefix = inner[0]
                if inner_prefix not in policies.allow_command_prefixes:
                    raise RuntimeError(
                        "Inner command "
                        f"`{inner_prefix}` not allowlisted. Allowed: {policies.allow_command_prefixes}"
                    )


def redact_text(text: str) -> str:
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(r"\1[REDACTED]", out)
    return out
