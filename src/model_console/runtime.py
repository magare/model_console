"""Runtime portability helpers.

Centralizes OS-aware behavior so command execution stays consistent across
macOS, Linux, and Windows without scattering platform conditionals.
"""

from __future__ import annotations

import ntpath
import platform
import posixpath
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Sequence


_POSIX_SHELLS = ("zsh", "bash", "sh")
_WINDOWS_SHELLS = ("pwsh", "powershell")
_WINDOWS_SHELL_FLAGS = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]
_POSIX_SHELL_FLAGS = ["-lc"]
_PYTHON_PATTERN = re.compile(r"^python(?:\d+(?:\.\d+)*)?(?:\.exe)?$")
_POWERSHELL_PREFIX_PATTERN = re.compile(
    r"""
    ^\s*
    (?:&\s*)?
    (?:
      "([^"]+)" |
      '([^']+)' |
      ([^\s;|&]+)
    )
    """,
    re.VERBOSE,
)


def current_system(system: str | None = None) -> str:
    """Return the active OS name using the same labels as platform.system()."""
    return (system or platform.system()).strip() or platform.system()


def is_windows(system: str | None = None) -> bool:
    return current_system(system).lower() == "windows"


def build_shell_command(command_text: str, *, system: str | None = None) -> list[str]:
    """Wrap an eval command in the platform-appropriate shell invocation."""
    shell = resolve_default_shell(system=system)
    if is_windows(system):
        return [shell, *_WINDOWS_SHELL_FLAGS, command_text]
    return [shell, *_POSIX_SHELL_FLAGS, command_text]


def resolve_default_shell(*, system: str | None = None) -> str:
    """Pick the best available shell for the active platform."""
    candidates = _WINDOWS_SHELLS if is_windows(system) else _POSIX_SHELLS
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return candidates[-1]


def resolve_mock_python_command(configured_cli: str | None) -> str:
    """Resolve a Python launcher for mock agents with a safe Windows fallback."""
    candidates: list[str] = []
    if configured_cli:
        candidates.append(configured_cli)
    if sys.executable:
        candidates.append(sys.executable)
    if is_windows():
        candidates.extend(["python", "py", "python3"])
    else:
        candidates.extend(["python3", "python"])

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _command_exists(normalized):
            return normalized

    if configured_cli:
        return configured_cli
    return sys.executable or ("python" if is_windows() else "python3")


def canonical_command_prefix(command: str) -> str:
    """Normalize executable names so equivalent launchers share one allowlist key."""
    name = _basename(command).lower()
    if name in {"py", "py.exe"} or _PYTHON_PATTERN.match(name):
        return "python"
    if name.endswith(".exe"):
        return name[:-4]
    return name


def extract_shell_expression(command: Sequence[str]) -> tuple[str, str] | None:
    """Return (shell_name, expression) when command is a supported shell wrapper."""
    if not command:
        return None

    shell_name = canonical_command_prefix(command[0])
    if shell_name in _POSIX_SHELLS:
        for index, token in enumerate(command[1:], start=1):
            if token in {"-lc", "-c"} and index + 1 < len(command):
                return shell_name, command[index + 1]
        return None

    if shell_name in _WINDOWS_SHELLS:
        for index, token in enumerate(command[1:], start=1):
            if token.lower() in {"-command", "-c"} and index + 1 < len(command):
                return shell_name, command[index + 1]
        return None

    return None


def extract_inner_command_prefix(shell_name: str, expression: str) -> str | None:
    """Best-effort parse of the first executable inside a shell expression."""
    if shell_name in _POSIX_SHELLS:
        try:
            parts = shlex.split(expression)
        except ValueError as exc:
            raise RuntimeError(f"Invalid shell command expression: {expression}") from exc
        return canonical_command_prefix(parts[0]) if parts else None

    if shell_name in _WINDOWS_SHELLS:
        match = _POWERSHELL_PREFIX_PATTERN.match(expression)
        if not match:
            raise RuntimeError(f"Invalid shell command expression: {expression}")
        raw_prefix = next((group for group in match.groups() if group), "")
        return canonical_command_prefix(raw_prefix) if raw_prefix else None

    return None


def _command_exists(command: str) -> bool:
    path = Path(command)
    if path.is_absolute():
        return path.exists()
    if any(sep in command for sep in ("/", "\\")):
        return path.exists()
    return shutil.which(command) is not None


def _basename(command: str) -> str:
    return ntpath.basename(posixpath.basename(command))
