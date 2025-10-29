from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, time, requests

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",
        "https://med-chat-delta.vercel.app",
        "http://127.0.0.1:5500"
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
if not HUGGINGFACE_API_KEY:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in environment")

API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
HEADERS = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}", "Content-Type": "application/json"}

def extract_user_message(payload: dict) -> str:
    if "message" in payload:
        return (payload.get("message") or "").strip()
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            c = (m.get("content") or "").strip()
            if c:
                return c
    return ""

@app.get("/")
def index():
    # Shows what routes are actually live
    return {
        "ok": True,
        "model": MODEL_ID,
        "routes": sorted([r.rule for r in app.url_map.iter_rules()])
    }

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

@app.get("/api/whoami")
def whoami():
    """Verify the HF token is valid on server."""
    r = requests.get(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
        timeout=30,
    )
    try:
        data = r.json()
    except Exception:
        data = {"text": r.text}
    return {"status": r.status_code, "data": data}

@app.get("/api/hf-test")
def hf_test():
    """Minimal test using text-generation format (works broadly)."""
    api_url = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
    # Mistral instruct format
    prompt = "<s>[INST] You are helpful. Say 'hi' in one short sentence. [/INST]"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 64,
            "temperature": 0.7,
            "top_p": 0.95,
            "do_sample": True,
            "return_full_text": False   # some providers ignore this; we handle either shape
        }
    }

    r = requests.post(api_url, headers=HEADERS, json=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"text": r.text}
    return {"status": r.status_code, "data": data}


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = extract_user_message(data)
    if not user_message:
        return jsonify({"reply": "Say something first."})

    # Build an instruction-style prompt for Mistral
    system = "You are a concise, accurate AI medical assistant for a pre-med student."
    # Compact instruction block
    instr = (
        f"{system}\n\n"
        f"User question: {user_message}\n"
        f"Rules: Keep it clear and correct. If uncertain, say so briefly."
    )
    prompt = f"<s>[INST] {instr} [/INST]"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 220,
            "temperature": 0.7,
            "top_p": 0.95,
            "do_sample": True,
            "return_full_text": False
        }
    }

    api_url = f"https://api-inference.huggingface.co/models/{MODEL_ID}"

    try:
        r = requests.post(api_url, headers=HEADERS, json=payload, timeout=60)
        # If model is cold-starting, HF returns 503; you can retry once if you want
        if r.status_code == 503:
            time.sleep(1.5)
            r = requests.post(api_url, headers=HEADERS, json=payload, timeout=60)

        r.raise_for_status()
        out = r.json()

        # Possible shapes:
        #   [{"generated_text":"..."}]
        #   {"generated_text":"..."}
        reply = ""
        if isinstance(out, list) and out and isinstance(out[0], dict):
            reply = (out[0].get("generated_text") or "").strip()
        elif isinstance(out, dict):
            reply = (out.get("generated_text") or "").strip()

        if not reply:
            reply = "…"

        return jsonify({"reply": reply})

    except requests.HTTPError as e:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        return jsonify({"reply": f"Server error: {e}; detail: {detail}"}), 502
    except Exception as e:
        return jsonify({"reply": f"Server error: {e}"}), 502
        
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
