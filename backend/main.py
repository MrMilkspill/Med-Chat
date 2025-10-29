from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import os
import time

load_dotenv()

app = Flask(__name__)

# Allow Vercel (all preview/prod) + your local live server
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",
        "http://127.0.0.1:5500"
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in environment")

# Bind client to the model we want (no task switching)
client = InferenceClient(model=MODEL_ID, token=HF_TOKEN)

def extract_user_message(payload: dict) -> str:
    # Supports both {message:"..."} and {messages:[{role,content},...]}
    if "message" in payload:
        return (payload["message"] or "").strip()
    msgs = payload.get("messages")
    if isinstance(msgs, list) and msgs:
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

    # Try once; if model is warming up (503), retry quickly
    for attempt in range(2):
        try:
            out = client.text_generation(
                prompt,
                max_new_tokens=220,
                temperature=0.7,
                do_sample=True,
                return_full_text=False
            )
            reply = (out or "").strip()
            if not reply:
                reply = "…"
            return jsonify({"reply": reply})
        except Exception as e:
            if attempt == 0:
                time.sleep(1.5)
                continue
            return jsonify({"reply": f"Server error: {e}"}), 502

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
