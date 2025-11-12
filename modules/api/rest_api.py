"""
REST API server module.

This module provides a Flask-based REST API for Desktop Agent, allowing
remote querying of system status and execution of predefined commands.

Endpoints:
    GET /status - Returns current system information
    POST /run - Executes a predefined command

Authentication:
    Supports Bearer token and query parameter authentication via API_AUTH_TOKEN.
"""

# Standard library imports
import logging
import secrets
import signal
import sys
from functools import wraps

# Third-party imports
from flask import Flask, jsonify, request

# Local imports
from modules.collectors.system import SystemInfoCollector
from modules.commands import run_predefined_command
from modules.config import API_AUTH_TOKEN

# Configure logger
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ----------------------------
# Authentication decorator
# ----------------------------

def require_auth(f):
    """
    Authentication decorator for API endpoints.

    Supports two authentication methods:
    1. Bearer token in Authorization header: Authorization: Bearer <token>
    2. Query parameter: ?auth_token=<token>

    If API_AUTH_TOKEN is not configured, allows access but logs a warning.
    This provides backward compatibility for existing installations.

    Security features:
    - Constant-time token comparison to prevent timing attacks
    - Logs failed authentication attempts with IP address
    - Returns standard 401 Unauthorized response
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If no auth token configured, allow access (backward compatibility)
        if not API_AUTH_TOKEN:
            logger.warning(f"API endpoint '{request.path}' accessed without authentication - auth_token not configured")
            return f(*args, **kwargs)

        provided_token = None

        # Check Authorization header (preferred method)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            provided_token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Check query parameter (alternative method)
        if not provided_token:
            provided_token = request.args.get('auth_token')

        # Validate token using constant-time comparison
        if provided_token and secrets.compare_digest(provided_token, API_AUTH_TOKEN):
            logger.debug(f"Successful authentication for '{request.path}' from {request.remote_addr}")
            return f(*args, **kwargs)

        # Authentication failed
        logger.warning(f"Unauthorized API access attempt to '{request.path}' from {request.remote_addr}")
        return jsonify({
            "error": "Unauthorized",
            "message": "Valid authentication token required. Use 'Authorization: Bearer <token>' header or '?auth_token=<token>' query parameter."
        }), 401

    return decorated_function


# ----------------------------
# Security headers middleware
# ----------------------------

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Note: Consider adding rate limiting in the future for additional security
    return response


# ----------------------------
# API endpoints
# ----------------------------

@app.route("/status")
@require_auth
def status():
    """
    GET /status
    Returns current system information.

    Authentication required if auth_token is configured.

    Returns:
        JSON object containing system information including CPU, memory,
        disk, network, GPU metrics, and system details.

    Example:
        >>> curl -H "Authorization: Bearer token123" http://localhost:5000/status
        {"cpu_usage": 25.5, "memory_usage": 45.2, ...}
    """
    try:
        collector = SystemInfoCollector()
        return jsonify(collector.collect_all())
    except Exception as e:
        logger.error(f"Error getting system info: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/run", methods=["POST"])
@require_auth
def run_command():
    """
    POST /run
    Executes a predefined command.

    Authentication required if auth_token is configured.

    Request body:
        {
            "command": "command_key"
        }

    Returns:
        JSON object with command execution result containing:
        - success: Boolean indicating if command succeeded
        - output: Command output or error message

    Example:
        >>> curl -X POST -H "Authorization: Bearer token123" \\
        ...      -H "Content-Type: application/json" \\
        ...      -d '{"command": "restart"}' \\
        ...      http://localhost:5000/run
        {"success": true, "output": "Command executed successfully"}
    """
    try:
        data = request.json
        command_key = data.get("command") if data else None

        if not command_key:
            logger.warning("No command key provided in request")
            return jsonify({"success": False, "output": "No command provided."}), 400

        result = run_predefined_command(command_key)
        return jsonify(result), 200 if result["success"] else 400

    except Exception as e:
        logger.error(f"Error running command: {e}", exc_info=True)
        return jsonify({"success": False, "output": "Internal server error"}), 500


def start_api(port, stop_event):
    """
    Start Flask API server with graceful shutdown support.

    Args:
        port: Port number to listen on
        stop_event: Threading event for shutdown signaling (currently not used)

    Note:
        Flask's built-in server doesn't natively support stop_event.
        For production, consider using a production WSGI server like gunicorn
        or waitress which support graceful shutdown.
    """
    logger.info(f"Starting API server on port {port}")

    # Suppress Flask's default logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    try:
        # Run Flask server
        # Note: In production, use gunicorn or waitress instead of Flask's dev server
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"API server error: {e}", exc_info=True)
    finally:
        logger.info("API server stopped")
