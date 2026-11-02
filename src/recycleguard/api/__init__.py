"""Local API application factory; no frontend implementation."""

from .app import ApiOptions, create_app

__all__ = ["ApiOptions", "create_app"]
