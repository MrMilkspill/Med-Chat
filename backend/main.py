# main.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, time, requests

load_dotenv()

app = Flask(__name__)

# CORS: your Vercel app + local Live Server
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

HEADERS = {
    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
    "Content-Type": "application/json"
}

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

def hf_generate(prompt: str, max_new_tokens=220, temperature=0.7, top_p=0.95):
    """
    Try:
      A) Inference API (text-generation)
      B) Router (OpenAI-compatible) /v1/completions  <-- NOT chat
    Returns: (reply_text, meta_dict) or raises HTTPError with both errors.
    """
    # ===== A) Classic Inference API (text-generation) =====
    api_a = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
    # Mistral instruct-style prompt
    prompt_a = f"<s>[INST] {prompt} [/INST]"
    payload_a = {
        "inputs": prompt_a,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "do_sample": True,
            "return_full_text": False
        }
    }
    try:
        ra = requests.post(api_a, headers=HEADERS, json=payload_a, timeout=60)
        if ra.status_code == 503:
            time.sleep(1.5)
            ra = requests.post(api_a, headers=HEADERS, json=payload_a, timeout=60)
        if ra.ok:
            try:
                out = ra.json()
            except Exception:
                out = {"text": ra.text}
            reply = ""
            if isinstance(out, list) and out and isinstance(out[0], dict):
                reply = (out[0].get("generated_text") or "").strip()
            elif isinstance(out, dict):
                reply = (out.get("generated_text") or "").strip()
            if reply:
                return reply, {"provider": "inference-api", "status": ra.status_code}
    except Exception:
        ra = None  # ensure defined

    # ===== B) Router (OpenAI-compatible) /v1/completions =====
    api_b = "https://router.huggingface.co/v1/completions"
    # Use same instruct prompt
    prompt_b = f"<s>[INST] {prompt} [/INST]"
    payload_b = {
        "model": MODEL_ID,
        "prompt": prompt_b,
        "max_tokens": max_new_tokens,
        "temperature": temperature,
        "top_p": top_p
    }
    try:
        rb = requests.post(api_b, headers=HEADERS, json=payload_b, timeout=60)
        if rb.ok:
            jb = rb.json()
            # OpenAI-style completions shape: choices[0].text
            try:
                txt = (jb["choices"][0]["text"] or "").strip()
            except Exception:
                txt = ""
            if txt:
                return txt, {"provider": "router-completions", "status": rb.status_code}
    except Exception:
        rb = None

    # If both failed, surface both errors
    a_status = getattr(ra, "status_code", "NA")
    a_text = getattr(ra, "text", "")[:400]
    b_status = getattr(rb, "status_code", "NA")
    b_text = getattr(rb, "text", "")[:400]
    raise requests.HTTPError(f"A failed: {a_status} {a_text}\nB failed: {b_status} {b_text}")

# ---------- Routes ----------
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

@app.get("/api/whoami")
def whoami():
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
    try:
        reply, meta = hf_generate("Say 'hi' in one short sentence.", max_new_tokens=32)
        return {"status": 200, "provider": meta["provider"], "reply": reply}
    except requests.HTTPError as e:
        return {"status": 502, "error": str(e)}

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = extract_user_message(data)
    if not user_message:
        return jsonify({"reply": "Say something first."})

    # Keep prompt simple & reliable for both providers
    system_note = "You are a concise, accurate AI medical assistant for a pre-med student. If uncertain, say so briefly."
    prompt = f"{system_note}\n\nUser question: {user_message}"

    try:
        reply, meta = hf_generate(prompt, max_new_tokens=220)
        return jsonify({"reply": reply, "meta": meta})
    except requests.HTTPError as e:
        return jsonify({"reply": f"Server error: {e}"}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
