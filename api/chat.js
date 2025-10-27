export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method Not Allowed" });
  }

  const HUGGINGFACE_API_KEY = process.env.HUGGINGFACE_API_KEY;
  const MODEL_ID = process.env.MODEL_ID || "mistralai/Mistral-7B-Instruct-v0.2";
  if (!HUGGINGFACE_API_KEY) return res.status(500).json({ error: "Missing API key" });

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

    if (r.status === 503) return res.status(200).json({ reply: "[Model is loading, try again shortly.]" });
    if (!r.ok) return res.status(502).json({ error: "Hugging Face error", detail: await r.text().catch(() => "") });

    const data = await r.json();
    let text = Array.isArray(data) && data[0]?.generated_text ? data[0].generated_text : data?.generated_text;
    if (!text) return res.status(500).json({ error: "No output text" });

    if (text.startsWith(prompt)) text = text.slice(prompt.length);
    return res.status(200).json({ reply: text.trim() });
  } catch (e) {
    return res.status(500).json({ error: "Server error", detail: e.message });
  }
}

function buildPrompt(messages) {
  let system = "You are a helpful assistant.";
  const lines = [];
  for (const m of messages || []) {
    const role = m.role || "user";
    const content = (m.content || "").trim();
    if (!content) continue;
    if (role === "system") system = content;
    else if (role === "assistant") lines.push(`Assistant: ${content}`);
    else lines.push(`User: ${content}`);
  }
  if (!lines.length) lines.push("User: Hello!");
  return `${system}\n${lines.join("\n")}\nAssistant:`;
}