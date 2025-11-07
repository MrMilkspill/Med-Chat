# app.py
import os, json, logging
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Logging that actually shows errors
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("med-chat")

# CORS: allow your Vercel URLs (comma-separated in env) + localhost
allowed = os.getenv("ALLOWED_ORIGINS",
                    "https://*.vercel.app,http://localhost:5500").split(",")
CORS(app, resources={r"/*": {
    "origins": allowed,
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

@app.get("/health")
def health():
    return {"ok": True}, 200

@app.post("/api/chat")
def api_chat():
    try:
        # Log raw body for debugging
        raw = request.get_data(cache=False, as_text=True)
        log.info("POST /api/chat raw: %s", raw[:500])

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Body must be JSON object"}), 400

        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return jsonify({"error": "messages must be a list"}), 400

        last = ""
        if messages and isinstance(messages[-1], dict):
            last = str(messages[-1].get("content") or "")

        # TODO: call your real model/service here
        reply_text = f"Echo: {last or 'hello'}"

        return jsonify({"reply": reply_text}), 200

    except Exception as e:
        # Log the full exception so you actually see why it 502'd
        log.exception("Error in /api/chat: %s", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Render sets PORT
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
