"""Compatibility wrapper for the legacy `model_console.reviews` module."""

from .core.reviews import default_rubric, has_blocking_fixes, merge_reviews, priority_rank

__all__ = ["default_rubric", "has_blocking_fixes", "merge_reviews", "priority_rank"]
