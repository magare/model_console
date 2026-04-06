"""Compatibility wrapper for the legacy `model_console.config` module."""

from .contracts.config import load_app_config

__all__ = ["load_app_config"]
