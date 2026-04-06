"""Compatibility wrapper for the legacy `model_console.transcript_viewer` module."""

from .observability.transcript_viewer import (
    default_viewer_output_path,
    load_transcript_entries,
    render_transcript_html,
    write_transcript_viewer,
)

__all__ = [
    "default_viewer_output_path",
    "load_transcript_entries",
    "render_transcript_html",
    "write_transcript_viewer",
]
