# main.py
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
        r"https://.*\.vercel\.app",     # any vercel.app
        "http://127.0.0.1:5500"         # VS Code Live Server
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# Use a public model that the Inference API serves without auth
MODEL_ID = os.getenv("MODEL_ID", "bigscience/bloom-560m")

def extract_user_message(payload: dict) -> str:
    if "message" in payload:
        return (payload.get("message") or "").strip()
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        # use the last non-empty message
        for m in reversed(msgs):
            c = (m.get("content") or "").strip()
            if c:
                return c
    return ""

def hf_generate(prompt: str, max_new_tokens=220, temperature=0.7, top_p=0.95):
    """
    Call HF Inference API (text-generation) WITHOUT Authorization header.
    Works for public models like bigscience/bloom-560m.
    """
    # No Mistral instruct tokens for BLOOM
    inputs = f"{prompt}\n"

    url = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
    payload = {
        "inputs": inputs,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "do_sample": True,
            "return_full_text": False
        }
    }
    headers = {"Content-Type": "application/json"}  # <-- intentionally no Authorization

    # initial try (model may cold-start)
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    if r.status_code == 503:
        time.sleep(1.5)
        r = requests.post(url, json=payload, headers=headers, timeout=60)

    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.text[:400]}")

    # response formats vary: list[{generated_text}] or {"generated_text":...}
    try:
        out = r.json()
    except Exception:
        out = {"raw": r.text}

    reply = ""
    if isinstance(out, list) and out and isinstance(out[0], dict):
        reply = (out[0].get("generated_text") or "").strip()
    elif isinstance(out, dict):
        reply = (out.get("generated_text") or "").strip()

    if not reply:
        # Some HF runtimes return {"error": "..."} with 200
        err = out.get("error") if isinstance(out, dict) else None
        raise requests.HTTPError(f"Empty generation. {('HF says: ' + err) if err else ''}")

    return reply

# ------------------ Routes ------------------

@app.get("/")
def index():
    return {
        "ok": True,
        "model": MODEL_ID,
        "routes": sorted([r.rule for r in app.url_map.iter_rules()])
    }

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

@app.get("/api/hf-test")
def hf_test():
    try:
        reply = hf_generate("Say 'hi' in three words.", max_new_tokens=16)
        return {"status": 200, "provider": "inference-api-public", "reply": reply}
    except Exception as e:
        return {"status": 502, "error": str(e)}

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = extract_user_message(data)
    if not user_message:
        return jsonify({"reply": "Say something first."})

    system_note = (
        "You are a concise, accurate AI medical assistant for a pre-med student. "
        "If uncertain, say so briefly."
    )
    prompt = f"{system_note}\n\nUser question: {user_message}"

    try:
        reply = hf_generate(prompt, max_new_tokens=220)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"Server error: {e}"}), 502

if __name__ == "__main__":
    # Render injects PORT; default to 5000 locally
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
