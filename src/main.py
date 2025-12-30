print("Smart mirror project ready 🚀")
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")

# Serve the UI
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "webface.html")

# API endpoint called by the phone UI
@app.post("/api/cmd")
def cmd():
    data = request.get_json(force=True) or {}
    cmd_name = data.get("cmd", "")

    # Match the strings used in .html: sendCmd('rate') / sendCmd('decide')
    if cmd_name == "rate":
        # TODO: put your real logic here (GPIO / run script / etc.)
        return jsonify({"ok": True, "output": "rate triggered"})

    if cmd_name == "decide":
        # TODO: put your real logic here
        return jsonify({"ok": True, "output": "decide triggered"})

    return jsonify({"ok": False, "error": "Invalid command"}), 400


if __name__ == "__main__":
    # Listen on all interfaces so your phone can reach it over Wi-Fi
    app.run(host="0.0.0.0", port=8080, debug=True)