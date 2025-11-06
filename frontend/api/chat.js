// /api/chat.js — safe version (uses env vars on Vercel)
export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method Not Allowed" });
  }

  const HUGGINGFACE_API_KEY = process.env.HUGGINGFACE_API_KEY;
  const MODEL_ID = process.env.MODEL_ID || "bigscience/bloom-560m";
  if (!HUGGINGFACE_API_KEY) return res.status(500).json({ error: "missing_token" });

  try {
    const { messages = [] } = req.body || {};
    const prompt = buildPrompt(messages);

    const r = await fetch(`https://api-inference.huggingface.co/models/${MODEL_ID}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${HUGGINGFACE_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        inputs: prompt,
        parameters: { max_new_tokens: 256, temperature: 0.7, top_p: 0.95 }
      })
    });

    if (r.status === 503) return res.status(200).json({ reply: "[Model is loading, try again in a few seconds.]" });
    if (!r.ok) return res.status(502).json({ error: "hf_error", detail: await r.text().catch(() => "") });

    const out = await r.json();
    let text = Array.isArray(out) && out[0]?.generated_text ? out[0].generated_text : out?.generated_text;
    if (!text) return res.status(500).json({ error: "bad_response" });

    if (text.startsWith(prompt)) text = text.slice(prompt.length);
    return res.status(200).json({ reply: text.trim() });
  } catch (e) {
    return res.status(500).json({ error: "server_error", detail: e.message });
  }
}

function buildPrompt(messages) {
  let system = "You are a helpful, concise assistant.";
  const parts = [];
  for (const m of messages || []) {
    const role = m.role || "user";
    const content = (m.content || "").trim();
    if (!content) continue;
    if (role === "system") system = content;
    else if (role === "assistant") parts.push(`Assistant: ${content}`);
    else parts.push(`User: ${content}`);
  }
  if (!parts.length) parts.push("User: Hello!");
  return `${system}\n${parts.join("\n")}\nAssistant:`;
}
