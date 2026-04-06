"""Compatibility wrapper for the legacy `model_console.validator` module."""

from .contracts.validator import validate_with_schema

__all__ = ["validate_with_schema"]
