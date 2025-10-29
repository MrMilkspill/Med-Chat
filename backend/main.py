from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import time
import requests

load_dotenv()

app = Flask(__name__)

def index():
    # shows the routes your server actually has right now
    return {
        "ok": True,
        "model": os.getenv("MODEL_ID"),
        "routes": sorted([str(r) for r in app.url_map.iter_rules()])
    }
# CORS: allow your Vercel site + local Live Server
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",   # any vercel deployment (prod + previews)
        "https://med-chat-delta.vercel.app",  # your known Vercel URL (explicit allow)
        "http://127.0.0.1:5500"       # local Live Server
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
if not HUGGINGFACE_API_KEY:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in environment")

API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
HEADERS = {
    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
    "Content-Type": "application/json"
}

def extract_user_message(payload: dict) -> str:
    """Accept either {message: "..."} or {messages:[{role,content},...]}."""
    if "message" in payload:
        return (payload.get("message") or "").strip()
    msgs = payload.get("messages")
    if isinstance(msgs, list) and msgs:
        # grab the last non-empty content
        for m in reversed(msgs):
            c = (m.get("content") or "").strip()
            if c:
                return c
    return ""

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = extract_user_message(data)
    if not user_message:
        return jsonify({"reply": "Say something first."})

    system = "You are a concise, accurate AI medical assistant for a pre-med student."
    prompt = f"System: {system}\nUser: {user_message}\nAssistant:"

    payload = {
        # Conversational task payload
        "inputs": {
            "text": prompt,
            "past_user_inputs": [],
            "generated_responses": []
        },
        "parameters": {
            "max_new_tokens": 220,
            "temperature": 0.7,
            "return_full_text": False
        }
    }

    # Retry once if the model is loading (503)
    for attempt in range(2):
        try:
            r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
            if r.status_code == 503 and attempt == 0:
                time.sleep(1.5)
                continue

            r.raise_for_status()
            out = r.json()

            # Possible shapes:
            # { "generated_text": "..." }
            # [ { "generated_text": "..." }, ... ]
            # { "conversation": { "generated_responses": ["..."] } }
            reply = ""
            if isinstance(out, dict):
                reply = (out.get("generated_text") or "").strip()
                if not reply:
                    conv = out.get("conversation") or {}
                    gen = conv.get("generated_responses") or []
                    if gen and isinstance(gen[0], str):
                        reply = gen[0].strip()
            elif isinstance(out, list) and out and isinstance(out[0], dict):
                reply = (out[0].get("generated_text") or "").strip()

            if not reply:
                reply = "…"

            return jsonify({"reply": reply})

        except requests.HTTPError as e:
            # Surface provider detail for quick debugging via Vercel Network → Response
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            if attempt == 0 and r.status_code == 503:
                time.sleep(1.5)
                continue
            return jsonify({"reply": f"Server error: {e}; detail: {detail}"}), 502
        except Exception as e:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return jsonify({"reply": f"Server error: {e}"}), 502

@app.get("/api/whoami")
def whoami():
    """Verify HF token validity on the server."""
    token = HUGGINGFACE_API_KEY or ""
    if not token:
        return {"ok": False, "error": "HUGGINGFACE_API_KEY missing"}, 500
    r = requests.get(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    try:
        data = r.json()
    except Exception:
        data = {"text": r.text}
    return {"status": r.status_code, "data": data}

@app.get("/api/hf-test")
def hf_test():
    """Send a minimal conversational request directly to the model."""
    token = HUGGINGFACE_API_KEY or ""
    api_url = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
    payload = {
        "inputs": {
            "text": "System: You are helpful.\nUser: Say hi.\nAssistant:",
            "past_user_inputs": [],
            "generated_responses": []
        },
        "parameters": {"max_new_tokens": 32, "temperature": 0.7, "return_full_text": False}
    }
    r = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    try:
        data = r.json()
    except Exception:
        data = {"text": r.text}
    return {"status": r.status_code, "data": data}

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

if __name__ == "__main__":
    # Local dev (Render will use gunicorn with $PORT)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
