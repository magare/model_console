"""Compatibility wrapper for the legacy `model_console.transcript` module."""

from .observability.transcript import (  # noqa: F401
    ProviderTrace,
    append_transcript_entry,
    extract_provider_trace,
    transcript_paths,
)

__all__ = [
    "ProviderTrace",
    "append_transcript_entry",
    "extract_provider_trace",
    "transcript_paths",
]
