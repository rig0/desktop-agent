from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/status")
def status():
    from modules.desktop_agent import get_system_info
    return jsonify(get_system_info())

@app.route("/run", methods=["POST"])
def run_command():
    from modules.commands import run_predefined_command
    data = request.json
    command_key = data.get("command")
    if not command_key:
        return jsonify({"success": False, "output": "No command provided."}), 400
    result = run_predefined_command(command_key)
    return jsonify(result), 200 if result["success"] else 400

def start_api(port):
    app.run(host="0.0.0.0", port=port)
