# main.py
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.2")  # stick to v0.2

if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in .env")

client = InferenceClient(model=MODEL_ID, token=HF_TOKEN)

def to_hf_messages(msgs):
    out = []
    for m in msgs or []:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role not in ("system", "user", "assistant"):
            role = "user"
        out.append({"role": role, "content": content})
    if not out:
        out = [{"role": "user", "content": "Hello!"}]
    return out

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    msgs = to_hf_messages(data.get("messages"))

    try:
        res = client.chat_completion(
            messages=msgs,
            max_tokens=256,
            temperature=0.7,
            top_p=0.95,
        )
        reply = res["choices"][0]["message"]["content"].strip()
        return jsonify({"reply": reply})
    except Exception as e:
        # log to server, don't dump into user chat
        app.logger.warning(f"chat_completion error: {e}")
        return jsonify({"error": "model_error", "detail": str(e)}), 502

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": MODEL_ID})

if __name__ == "__main__":
    # keep local dev simple (HTTP); switch to adhoc HTTPS only if you’ve installed cryptography
    app.run(host="127.0.0.1", port=5000, debug=True)
    # app.run(host="127.0.0.1", port=5000, debug=True, ssl_context="adhoc")