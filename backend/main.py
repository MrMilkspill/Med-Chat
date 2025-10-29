from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Allow both local and Vercel frontends
CORS(app, resources={r"/*": {
    "origins": [
        r"https://.*\.vercel\.app",   # any vercel deployment
        "http://127.0.0.1:5500"       # local live server
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# Hugging Face credentials
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in .env")

client = InferenceClient(token=HF_TOKEN)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}

    # Handle both message formats
    if "message" in data:
        user_message = (data["message"] or "").strip()
    elif "messages" in data and isinstance(data["messages"], list):
        user_message = (data["messages"][-1].get("content") or "").strip()
    else:
        user_message = ""

    if not user_message:
        return jsonify({"reply": "Say something first."})

    try:
        # Try using chat.completions (new API)
        completion = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a concise, knowledgeable AI medical assistant who provides accurate, professional, and clear explanations to pre-med students."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=256,
            temperature=0.7,
            top_p=0.95
        )
        reply = completion.choices[0].message.content.strip()

    except Exception:
        # Fallback for models that don’t support chat.completions
        prompt = (
            "System: You are a concise, knowledgeable AI medical assistant.\n"
            f"User: {user_message}\nAssistant:"
        )
        reply = client.text_generation(
            prompt,
            max_new_tokens=220,
            temperature=0.7,
            do_sample=True,
            return_full_text=False
        ).strip()

    return jsonify({"reply": reply})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
