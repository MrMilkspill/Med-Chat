// server/server.js
import express from "express";
import cors from "cors";
import dotenv from "dotenv";

dotenv.config();
const app = express();
app.use(cors());
app.use(express.json());

const SEARCH_API_URL = process.env.SEARCH_API_URL;
const SEARCH_API_KEY = process.env.SEARCH_API_KEY;
const PORT = process.env.PORT || 8787;

// Generic search proxy (needs real API)
app.get("/api/search", async (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.status(400).json({ error: "Missing q" });
  if (!SEARCH_API_URL || !SEARCH_API_KEY) {
    return res.status(501).json({ error: "Search API not configured" });
  }
  try {
    const r = await fetch(`${SEARCH_API_URL}?q=${encodeURIComponent(q)}&num=5`, {
      headers: {
        "Authorization": `Bearer ${SEARCH_API_KEY}`,
        "Accept": "application/json"
      }
    });
    const data = await r.json();
    const items = normalizeResults(data);
    res.json({ query: q, results: items });
  } catch (e) {
    res.status(500).json({ error: e.message || "Search failed" });
  }
});

// Free Wikipedia fallback
app.get("/api/wiki", async (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.status(400).json({ error: "Missing q" });
  try {
    const r = await fetch(`https://en.wikipedia.org/w/rest.php/v1/search/title?q=${encodeURIComponent(q)}&limit=5`);
    const data = await r.json();
    const items = (data.pages || []).map(p => ({
      title: p.title,
      url: `https://en.wikipedia.org/wiki/${encodeURIComponent(p.title.replace(/\s+/g, "_"))}`,
      snippet: p.description || "No description"
    }));
    res.json({ query: q, results: items });
  } catch (e) {
    res.status(500).json({ error: e.message || "Wiki failed" });
  }
});

function normalizeResults(data) {
  const items = data.results || data.items || data.data || [];
  return items.slice(0, 5).map(it => ({
    title: it.title || it.name || "Untitled",
    url: it.url || it.link || "#",
    snippet: it.snippet || it.description || ""
  }));
}

app.listen(PORT, () => {
  console.log(`Server listening on http://localhost:${PORT}`);
});