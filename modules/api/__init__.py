"""REST API for Desktop Agent.

This package provides a Flask-based REST API for querying system status
and executing predefined commands remotely.

Modules:
    rest_api: Flask application and API endpoints
"""

from .rest_api import start_api, app

__all__ = ["start_api", "app"]
