/* One-user chat with an API-backed bot.
   - Messages saved in localStorage.
   - Bot replies by calling your backend at /api/chat (base URL from runtime env).
   - Falls back to a local offline bot if the request fails.
*/

const storageKey = "solo-chat-v1";

// Pull API_BASE from the env snippet served at /api/runtime-config.js
const API_BASE = ((window.RUNTIME_CONFIG && window.RUNTIME_CONFIG.API_BASE) || "").replace(/\/+$/, "");
if (!API_BASE) {
  console.error("API_BASE is missing. Set it in Vercel env (API_BASE) and redeploy.");
}

const $ = (s, el = document) => el.querySelector(s);
const messageList = $("#messageList");
const composer = $("#composer");
const nameInput = $("#nameInput");
const messageInput = $("#messageInput");
const typingEl = $("#typing");
const clearBtn = $("#clearChat");

let messages = load(storageKey) || seed();

renderAll();
scrollToBottom();

composer.addEventListener("submit", e => {
  e.preventDefault();
  const author = (nameInput.value || "You").trim();
  const text = messageInput.value.trim();
  if (!text) return;

  addMessage({ author, role: "user", text });
  messageInput.value = "";
  autoGrow(messageInput);

  respond(text);
});

messageInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.requestSubmit();
  }
});
messageInput.addEventListener("input", () => autoGrow(messageInput));

clearBtn.addEventListener("click", () => {
  if (!confirm("Clear all messages?")) return;
  messages = [];
  save(storageKey, messages);
  renderAll();
});

/* BOT RESPONSE PIPELINE */
async function respond(userText){
  showTyping(true);
  await delay(fakeLatency(userText));

  let reply;
  try {
    const history = messages.slice(-20).map(m => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: m.text
    }));
    reply = await callYourApi(history);
  } catch (err) {
    console.error("Falling back to local bot:", err);
    reply = await localBot(userText, messages);
  }

  showTyping(false);
  addMessage({ author: "AI", role: "assistant", text: reply });
}

/* Real API call to your backend */
async function callYourApi(history){
  if (!API_BASE) throw new Error("API_BASE not set");
  let r;
  try {
    r = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history })
    });
  } catch (netErr) {
    console.error("Network error hitting backend:", netErr);
    throw new Error("Network error contacting backend");
  }

  let data = null;
  try {
    data = await r.json();
  } catch (parseErr) {
    const text = await r.text().catch(()=>"(no body)");
    console.error("Non-JSON response body:", text);
    throw new Error(`Bad non-JSON response (${r.status})`);
  }

  if (!r.ok) {
    const detail = data && (data.detail || data.error || data.reply) ? ` (${data.detail || data.error || data.reply})` : "";
    throw new Error(`API error ${r.status}${detail}`);
  }

  if (!data || typeof data.reply !== "string") {
    console.error("Bad response shape:", data);
    throw new Error("Bad response shape from server");
  }
  return data.reply.trim();
}

/* Local offline bot fallback */
async function localBot(query, history){
  const q = query.trim();
  const lower = q.toLowerCase();

  if (/\b(hi|hello|hey|yo|sup)\b/i.test(q)) {
    return "Hey. What do you need?";
  }
  if (/\b(time|clock)\b/i.test(q)) {
    return "Current time: " + new Date().toLocaleTimeString();
  }
  if (/\b(date|day|today)\b/i.test(q)) {
    return "Today is " + new Date().toLocaleDateString(undefined, { weekday:"long", year:"numeric", month:"long", day:"numeric" });
  }

  const mathMatch = lower.match(/(?:^|\b)(?:what\s+is|calculate|calc|=)\s*([0-9\.\s\+\-\*\/\(\)\^%]+)\s*\??$/i);
  if (mathMatch) {
    const expr = mathMatch[1];
    try {
      const safe = expr.replace(/\^/g,"**");
      if (!/^[0-9\.\s\+\-\*\/\(\)%\**]+$/.test(safe)) throw new Error("bad");
      // eslint-disable-next-line no-new-func
      const result = Function(`"use strict"; return (${safe});`)();
      if (typeof result === "number" && isFinite(result)) {
        return `${expr.trim()} = ${result}`;
      }
    } catch {}
    return "That expression didn’t compute. Try something simpler.";
  }

  const kwMatch = lower.match(/\b(search|find|look\s*for)\s+(.+)/i);
  if (kwMatch) {
    const term = kwMatch[2].trim().toLowerCase();
    const hits = history
      .filter(m => m.role === "user" && m.text.toLowerCase().includes(term))
      .slice(-5);
    if (!hits.length) return `Nothing in our chat mentions “${term}.” Try saying the thing first, then ask me to find it.`;
    const bullets = hits.map(h => "• " + h.text).join("\n");
    return `Found ${hits.length} recent ${hits.length===1?"message":"messages"} mentioning “${term}”:\n${bullets}`;
  }

  return "Got it. Wire this to the real API for smarter answers.";
}

/* UI + storage */
function addMessage({ author, role, text }){
  const msg = { id: crypto.randomUUID(), author, role, text, ts: new Date().toISOString() };
  messages.push(msg);
  save(storageKey, messages);
  renderMessage(msg);
  scrollToBottom();
}
function renderAll(){
  messageList.innerHTML = "";
  messages.forEach(renderMessage);
}
function renderMessage(m){
  const li = document.createElement("li");
  li.className = "msg" + (m.role === "user" ? " me" : "");
  li.id = "msg-"+m.id;
  li.innerHTML = `
    <div class="avatar" aria-hidden="true"></div>
    <div class="bubble">
      <div class="meta">
        <span class="who">${escapeHtml(m.author)}</span>
        <span class="when" title="${m.ts}">${formatTime(m.ts)}</span>
      </div>
      <div class="text">${linkify(escapeHtml(m.text))}</div>
    </div>
  `;
  messageList.appendChild(li);
}
function scrollToBottom(){ messageList.scrollTop = messageList.scrollHeight; }
function showTyping(v){ typingEl.hidden = !v; }
function autoGrow(el){ el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 220) + "px"; }
function delay(ms){ return new Promise(r => setTimeout(r, ms)); }
function fakeLatency(text){
  const base = 300 + Math.min(1200, text.length * 12);
  const jitter = Math.random() * 400;
  return base + jitter;
}

/* utils */
function save(k,v){ localStorage.setItem(k, JSON.stringify(v)); }
function load(k){ try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } }
function escapeHtml(s){ return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function linkify(s){ return s.replace(/\b(https?:\/\/[^\s<]+)\b/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'); }
function formatTime(ts){ const d=new Date(ts); return d.toLocaleString([], {year:"numeric",month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"}); }

function seed(){
  const now = Date.now();
  const demo = [
    { id: crypto.randomUUID(), author:"AI", role:"assistant", text:"Welcome. I’m online-capable now. If the server dies, I fall back offline.", ts:new Date(now-60000).toISOString() }
  ];
  save(storageKey, demo);
  return demo;
}
