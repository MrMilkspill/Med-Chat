# app.py
import os, logging
from flask import Flask, request, jsonify, make_response
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # good hygiene on Render

log = logging.getLogger("med-chat")
logging.basicConfig(level=logging.INFO)

ALLOWED = set([o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()])

def _corsify(resp):
    origin = request.headers.get("Origin")
    if origin and (origin in ALLOWED):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        # If you ever use cookies/credentials, also set:
        # resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp

@app.route("/health", methods=["GET"])
def health():
    return _corsify(jsonify({"ok": True}))

@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    # 1) Handle preflight cleanly
    if request.method == "OPTIONS":
        return _corsify(make_response(("", 204)))

    # 2) Handle real POST
    try:
        data = request.get_json(silent=True) or {}
        messages = data.get("messages", [])
        last = messages[-1].get("content") if messages and isinstance(messages[-1], dict) else "hello"
        reply = f"Echo: {last}"
        return _corsify(jsonify({"reply": reply}))
    except Exception as e:
        log.exception("Error in /api/chat")
        return _corsify(jsonify({"error": str(e)})), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
