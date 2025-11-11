# Standard library imports
import logging
import signal
import sys

# Third-party imports
from flask import Flask, jsonify, request

# Configure logger
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/status")
def status():
    try:
        from modules.desktop_agent import get_system_info
        return jsonify(get_system_info())
    except Exception as e:
        logger.error(f"Error getting system info: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/run", methods=["POST"])
def run_command():
    try:
        from modules.commands import run_predefined_command
        data = request.json
        command_key = data.get("command")
        if not command_key:
            logger.warning("No command key provided in request")
            return jsonify({"success": False, "output": "No command provided."}), 400
        result = run_predefined_command(command_key)
        return jsonify(result), 200 if result["success"] else 400
    except Exception as e:
        logger.error(f"Error running command: {e}", exc_info=True)
        return jsonify({"success": False, "output": "Internal server error"}), 500

def start_api(port, stop_event):
    """Start Flask API server with graceful shutdown support."""
    logger.info(f"Starting API server on port {port}")

    # Suppress Flask's default logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    try:
        # Note: Flask's built-in server doesn't natively support stop_event
        # For production, consider using a production WSGI server like gunicorn
        # For now, we'll run Flask normally but with proper error handling
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"API server error: {e}", exc_info=True)
    finally:
        logger.info("API server stopped")
