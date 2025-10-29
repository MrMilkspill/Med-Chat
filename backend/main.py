from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
import os
from dotenv import load_dotenv
import re

load_dotenv()

HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")  # use your existing key var
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

assert HF_TOKEN, "Missing HUGGINGFACE_API_KEY in environment!"

client = InferenceClient(token=HF_TOKEN)

app = Flask(__name__)
CORS(app)

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"reply": "Say something first."})

    # Simple identity messages
    canned = {
        "who are you": "I'm an AI assistant who can answer questions, explain topics, or just chat.",
        "what can you do": "I can summarize, research, or generate answers across science, medicine, or anything you throw at me.",
        "hello": "Hey there! What do you want to talk about?",
        "hi": "Hey there! How’s it going?"
    }
    for key, text in canned.items():
        if re.search(rf"\b{re.escape(key)}\b", user_message.lower()):
            return jsonify({"reply": text})

    # Prepare messages for chat completion
    messages = [
        {"role": "system", "content": "You are a knowledgeable AI assistant. Be clear and concise."},
        {"role": "user", "content": user_message}
    ]

    try:
        completion = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            max_tokens=400,
            temperature=0.7,
        )
        ai_reply = completion.choices[0].message.content
        return jsonify({"reply": ai_reply})
    except Exception as e:
        print("Error from model:", e)
        return jsonify({"reply": f"Server error: {e}"}), 502

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_ID}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
