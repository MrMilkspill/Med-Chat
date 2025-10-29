from flask import Flask, request, jsonify
from flask_cors import CORS
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Replace <your-vercel-project> with your actual Vercel URL (no https:// if you want)
CORS(app, resources={r"/*": {"origins": [
    "https://med-chat-delta.vercel.app/",   # whatever your actual vercel domain is
    "http://127.0.0.1:5500"
]}})


HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
MODEL_ID = os.getenv("MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")

if not HF_TOKEN:
    raise RuntimeError("Missing HUGGINGFACE_API_KEY in .env")

client = InferenceClient(token=HF_TOKEN)

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}

    # Handle both 'message' and 'messages'
    if "message" in data:
        user_message = (data["message"] or "").strip()
    elif "messages" in data and isinstance(data["messages"], list):
        user_message = (data["messages"][-1].get("content") or "").strip()
    else:
        user_message = ""

    if not user_message:
        return jsonify({"reply": "Say something first."})

    try:
        completion = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a concise, knowledgeable AI medical assistant who gives clear and accurate information to students."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=256,
            temperature=0.7,
            top_p=0.95
        )
        reply = completion.choices[0].message.content.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        print("Model error:", e)
        return jsonify({"reply": "Sorry, something went wrong with the model."}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
