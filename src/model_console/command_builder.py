"""Compatibility wrapper for the legacy `model_console.command_builder` module."""

from .agents.command_builder import build_agent_command, select_provider_output_text

__all__ = ["build_agent_command", "select_provider_output_text"]
