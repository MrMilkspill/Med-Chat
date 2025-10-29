from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import time
import requests

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",   # any vercel deployment (prod + previews)
        "http://127.0.0.1:5500"       # local Live Server
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in environment")

API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

def extract_user_message(payload: dict) -> str:
    if "message" in payload:
        return (payload["message"] or "").strip()
    msgs = payload.get("messages")
    if isinstance(msgs, list):
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
        # Conversational pipeline expects inputs in this shape
        "inputs": {
            "text": prompt,
            "past_user_inputs": [],
            "generated_responses": []
        },
        # Optional generation parameters
        "parameters": {
            "max_new_tokens": 220,
            "temperature": 0.7,
            "return_full_text": False
        }
    }

    # Retry once if the model is warming up (503)
    for attempt in range(2):
        try:
            r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
            # 503 => model loading; backoff then retry
            if r.status_code == 503 and attempt == 0:
                time.sleep(1.5)
                continue

            # Raise for other http errors so we can surface them
            r.raise_for_status()
            data = r.json()

            # Possible shapes:
            # { "generated_text": "..." }  OR  [ { "generated_text": "..." }, ... ]
            reply = ""
            if isinstance(data, dict):
                reply = (data.get("generated_text") or "").strip()
                # Some providers return {"conversation": {"generated_responses": [...]} }
                if not reply:
                    conv = data.get("conversation") or {}
                    gen = conv.get("generated_responses") or []
                    if gen and isinstance(gen[0], str):
                        reply = gen[0].strip()
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                reply = (data[0].get("generated_text") or "").strip()

            if not reply:
                reply = "…"

            return jsonify({"reply": reply})

        except requests.HTTPError as e:
            # Surface provider message for debugging in Vercel Network → Response
            try:
                err = r.json()
            except Exception:
                err = r.text
            if attempt == 0 and r.status_code == 503:
                time.sleep(1.5)
                continue
            return jsonify({"reply": f"Server error: {e}; detail: {err}"}), 502
        except Exception as e:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return jsonify({"reply": f"Server error: {e}"}), 502

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=5000, debug=True)
