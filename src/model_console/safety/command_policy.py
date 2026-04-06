"""Safety guardrails.

assert_command_safe() enforces allow/deny command policies before any
subprocess is executed.  redact_text() scrubs secrets (API keys, tokens,
passwords) from strings before they are persisted to logs.
"""

from __future__ import annotations

import re

from ..models import Policies
from ..runtime import canonical_command_prefix, extract_inner_command_prefix, extract_shell_expression


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

    allowed_prefixes = {canonical_command_prefix(prefix) for prefix in policies.allow_command_prefixes}
    if policies.allow_command_prefixes:
        prefix = canonical_command_prefix(command[0]) if command else ""
        shell_expression = extract_shell_expression(command)

        if prefix not in allowed_prefixes and shell_expression is None:
            raise RuntimeError(
                f"Command `{command[0] if command else ''}` not allowlisted. "
                f"Allowed: {policies.allow_command_prefixes}"
            )

        if shell_expression is not None:
            shell_name, expression = shell_expression
            inner_prefix = extract_inner_command_prefix(shell_name, expression)
            if inner_prefix and inner_prefix not in allowed_prefixes:
                raise RuntimeError(
                    "Inner command "
                    f"`{inner_prefix}` not allowlisted. Allowed: {policies.allow_command_prefixes}"
                )


def redact_text(text: str) -> str:
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(r"\1[REDACTED]", out)
    return out
