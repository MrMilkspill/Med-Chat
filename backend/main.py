import os, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY") or ""
# Optional: let you force a model via env; otherwise we’ll auto-pick
PREFERRED_MODEL = os.getenv("MODEL_ID", "").strip() or None

# A small, public set that normally works on HF Serverless right now.
# Order matters. We’ll try each until one accepts your token.
FALLBACK_MODELS = [
    # text-generation (causal) family
    "bigscience/bloom-560m",
    "distilgpt2",
    "facebook/blenderbot-400M-distill",  # dialog-ish, still returns generated_text
    # text2text family (also returns generated_text on HF serverless)
    "google/flan-t5-small"
]

ACTIVE_MODEL = None  # will be filled after first successful call

def _hf_infer(model_id: str, prompt: str, max_new_tokens=120, temperature=0.7):
    r = requests.post(
        f"https://api-inference.huggingface.co/models/{model_id}",
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={"inputs": prompt, "parameters": {"max_new_tokens": max_new_tokens, "temperature": temperature}},
        timeout=60,
    )
    # HF returns 503 while a model spins up; treat as retryable error
    if r.status_code == 503:
        return None, {"type": "loading", "detail": "Model loading"}
    if r.status_code >= 400:
        # Pass back the JSON for inspection (usually includes code=model_not_supported)
        try:
            return None, r.json()
        except Exception:
            return None, {"type": "http_error", "status": r.status_code, "text": r.text}
    try:
        out = r.json()
    except Exception as e:
        return None, {"type": "bad_json", "detail": str(e)}
    # Common HF response shape for serverless text gen
    if isinstance(out, list) and out and "generated_text" in out[0]:
        return out[0]["generated_text"], None
    # Fallback: just stringify whatever we got
    return str(out), None

def _choose_model(prompt: str):
    # 1) If user set PREFERRED_MODEL, try it first
    candidates = ([PREFERRED_MODEL] if PREFERRED_MODEL else []) + FALLBACK_MODELS
    tried_errors = []
    for m in candidates:
        txt, err = _hf_infer(m, prompt, max_new_tokens=8)  # tiny probe
        if err:
            # If explicitly “model_not_supported”, skip to next
            if (isinstance(err, dict) and err.get("code") == "model_not_supported") or \
               ("model_not_supported" in str(err).lower()):
                tried_errors.append((m, "not_supported"))
                continue
            # If loading, just keep trying this one once more quickly
            if isinstance(err, dict) and err.get("type") == "loading":
                txt, err = _hf_infer(m, prompt, max_new_tokens=8)
                if not err:
                    return m
            tried_errors.append((m, str(err)))
            continue
        # worked
        return m
    # If nothing worked, report the last few errors for debugging
    raise RuntimeError(f"No supported models for this token. Tried: {tried_errors[:4]}")

@app.post("/api/chat")
def chat():
    global ACTIVE_MODEL
    data = request.get_json(silent=True) or {}
    msgs = data.get("messages") or []
    prompt = "\n".join((m.get("content") or "").strip() for m in msgs if (m.get("content") or "").strip())
    if not prompt:
        prompt = "Hello."

    try:
        # Pick a model once and cache it
        if not ACTIVE_MODEL:
            ACTIVE_MODEL = _choose_model(prompt)
        # Generate for real
        full_text, err = _hf_infer(ACTIVE_MODEL, prompt, max_new_tokens=200, temperature=0.7)
        if err:
            # If the active model suddenly becomes unsupported, re-choose once
            if (isinstance(err, dict) and err.get("code") == "model_not_supported") or \
               ("model_not_supported" in str(err).lower()):
                ACTIVE_MODEL = None
                ACTIVE_MODEL = _choose_model(prompt)
                full_text, err = _hf_infer(ACTIVE_MODEL, prompt, max_new_tokens=200, temperature=0.7)
        if err:
            return jsonify({"error": "hf_error", "detail": err}), 502

        # Strip the prompt prefix if the backend echoed it
        reply = full_text[len(prompt):].strip() if full_text.startswith(prompt) else full_text.strip()
        return jsonify({"reply": reply, "model": ACTIVE_MODEL})
    except Exception as e:
        return jsonify({"error": "server_error", "detail": str(e)}), 502

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": ACTIVE_MODEL or PREFERRED_MODEL or FALLBACK_MODELS[0]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
