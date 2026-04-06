"""Compatibility wrapper for the legacy `model_console.mock_agent` module."""

from .agents.mock import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
