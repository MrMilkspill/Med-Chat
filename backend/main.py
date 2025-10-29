# main.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
import os
import re

load_dotenv()

# -------- Config --------
HF_TOKEN  = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
MODEL_ID  = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
PORT      = int(os.getenv("PORT", "5000"))

if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY (or HF_TOKEN) in env.")

client = InferenceClient(token=HF_TOKEN)

# -------- App / CORS --------
app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",
        "http://127.0.0.1:5500"
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# -------- Helpers --------
IDENTITY = {
    "who are you": "I’m an AI medical study assistant. I answer clearly and briefly.",
    "what can you do": "I can explain concepts, generate study prompts, and help with quick recall.",
    "hello": "Hey. What do you need help with?",
    "hi": "Hi. What topic are we grinding today?"
}

def extract_user_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    # support your current frontend shape
    msgs = payload.get("messages")
    if isinstance(msgs, list) and msgs:
        # use last non-empty content
        for m in reversed(msgs):
            c = (m.get("content") or "").strip()
            if c:
                return c
    # alternate shape: { "message": "..." }
    return (payload.get("message") or "").strip()

def build_instruct_prompt(user_text: str) -> str:
    system = (
        "You are a concise, accurate AI medical assistant for a pre-med student. "
        "Cite concepts, be brief, say when uncertain."
    )
    # Simple instruct wrapper that works with instruct-tuned text-gen models
    return f"<s>[INST] {system}\n\nUser: {user_text}\nAssistant: [/INST]"

# -------- Routes --------
@app.get("/")
def root():
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
        # Try chat first
        chat = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": "Say hi in three words."}],
            max_tokens=24
        )
        txt = (chat.choices[0].message.content or "").strip()
        if not txt:
            raise RuntimeError("empty chat reply")
        return {"status": 200, "mode": "chat", "reply": txt}
    except Exception as _:
        # Fallback to text-generation
        try:
            prompt = build_instruct_prompt("Say hi in three words.")
            txt = client.text_generation(
                model=MODEL_ID,
                prompt=prompt,
                max_new_tokens=24,
                temperature=0.7,
                top_p=0.95,
                do_sample=True,
                return_full_text=False
            ).strip()
            return {"status": 200, "mode": "text-generation", "reply": txt}
        except Exception as e2:
            return {"status": 502, "error": str(e2)}

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_text = extract_user_text(data)

    if not user_text:
        # mirror your friend’s style
        return jsonify({"reply": "Please say something so I can help!"})

    # quick static replies (like your friend’s)
    for key, resp in IDENTITY.items():
        if re.search(r"\b" + re.escape(key) + r"\b", user_text.lower()):
            return jsonify({"reply": resp})

    # 1) Try chat endpoint (works only if your HF token’s provider supports it)
    try:
        chat = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a concise medical study assistant."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=220,
            temperature=0.7,
            top_p=0.95
        )
        txt = (chat.choices[0].message.content or "").strip()
        if txt:
            return jsonify({"reply": txt, "meta": {"mode": "chat"}})
    except Exception:
        pass  # fall through to text-gen

    # 2) Fallback: text-generation with an instruct prompt
    try:
        prompt = build_instruct_prompt(user_text)
        txt = client.text_generation(
            model=MODEL_ID,
            prompt=prompt,
            max_new_tokens=220,
            temperature=0.7,
            top_p=0.95,
            do_sample=True,
            return_full_text=False
        ).strip()
        return jsonify({"reply": txt, "meta": {"mode": "text-generation"}})
    except Exception as e2:
        return jsonify({"reply": f"Sorry, something went wrong. {e2}"}), 502

# -------- Entrypoint --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
