from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import os

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

# Bind client to specific model
client = InferenceClient(model=MODEL_ID, token=HF_TOKEN)

def extract_user_message(payload: dict) -> str:
    """Accept {message: "..."} or {messages:[{role,content},...]}."""
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

    # ✅ Define these BEFORE try:
    system = "You are a concise, accurate AI medical assistant for a pre-med student."
    prompt = f"System: {system}\nUser: {user_message}\nAssistant:"

    try:
        # Provider supports 'conversational' for this model
        conv_out = client.conversational(
            text=prompt,
            past_user_inputs=[],
            generated_responses=[]
        )

        # HF typically returns dict with 'generated_text'
        reply = ""
        if isinstance(conv_out, dict):
            reply = (conv_out.get("generated_text") or "").strip()
        elif isinstance(conv_out, list) and conv_out and isinstance(conv_out[0], dict):
            reply = (conv_out[0].get("generated_text") or "").strip()

        if not reply:
            reply = "…"

        return jsonify({"reply": reply})

    except Exception as e:
        # Surface real error to Vercel Network → Response
        return jsonify({"reply": f"Server error: {e}"}), 502

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=5000, debug=True)
