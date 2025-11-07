// api/runtime-config.js
export default function handler(req, res) {
  const base = process.env.API_BASE || "";
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "public, max-age=60");
  // Expose at runtime for plain JS to read.
  res.end(`window.RUNTIME_CONFIG = { API_BASE: ${JSON.stringify(base)} };`);
}
