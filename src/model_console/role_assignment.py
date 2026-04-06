"""Compatibility wrapper for the legacy `model_console.role_assignment` module."""

from .core.role_assignment import AssignmentContext, RoleAssignmentEngine

__all__ = ["AssignmentContext", "RoleAssignmentEngine"]
