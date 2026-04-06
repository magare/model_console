"""Compatibility wrapper for the legacy `model_console.eval` module."""

from .agents.eval import run_eval_commands

__all__ = ["run_eval_commands"]
