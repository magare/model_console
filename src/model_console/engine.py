"""Compatibility wrapper for the legacy `model_console.engine` module."""

from .core.engine import LoopEngine, _default_rubric

__all__ = ["LoopEngine", "_default_rubric"]
