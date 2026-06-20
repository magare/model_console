"""model_console – CLI orchestration framework for multi-agent implement/review loops.

Coordinates AI agents (Claude, Codex, Gemini, etc.) to iteratively produce
and review artifacts, with git integration, safety policies, and run retention.

Public API:
    - LoopEngine: Main orchestration engine
    - RunState, Assignment: Core data models
    - AppConfig, AgentConfig, LoopConfig: Configuration models
    - mc: CLI entry point (use via `python -m model_console`)
"""

from __future__ import annotations

# Re-export core public API
from .core import LoopEngine, RunState
from .models import AppConfig, AgentConfig, Assignment, LoopConfig

__all__ = [
    "__version__",
    # Core engine
    "LoopEngine",
    # Data models
    "AppConfig",
    "AgentConfig",
    "Assignment",
    "LoopConfig",
    "RunState",
]

__version__ = "0.1.0"
