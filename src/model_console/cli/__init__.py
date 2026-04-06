"""CLI package preserving the historic `model_console.cli` entry point."""

from .app import build_parser, cmd_resume, cmd_run, cmd_status, cmd_transcript, main

__all__ = [
    "build_parser",
    "cmd_resume",
    "cmd_run",
    "cmd_status",
    "cmd_transcript",
    "main",
]
