"""Compatibility wrapper for the legacy `model_console.prompts` module."""

from .contracts.prompts import load_template, render_template

__all__ = ["load_template", "render_template"]
