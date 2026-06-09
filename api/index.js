// Thin serverless API for the Vercel demo of Video Nuggets OS.
//
// The real FastAPI backend (live ffmpeg/Edge-TTS render pipeline + ChromaDB RAG)
// lives in backend/ and runs locally. For the cloud demo we serve the
// pre-rendered seed library as static assets and back the handful of read-only
// routes the UI needs from this single function, plus a grounded chatbot that
// retrieves over the committed transcripts (and uses Groq Llama-3 if a key is
// configured, falling back to a deterministic synthesizer otherwise).

const library = require('./_data/library.json');
const videos = require('./_data/videos.json');
const corpus = require('./_data/corpus.json');

const DEMO_USERS = {
  admin: { password: 'admin123', user: { id: 1, username: 'admin', display_name: 'Demo Admin', role: 'admin', email: 'admin@demo.local' } },
  viewer: { password: 'viewer123', user: { id: 2, username: 'viewer', display_name: 'Demo Viewer', role: 'viewer', email: 'viewer@demo.local' } },
};

const STOPWORDS = new Set('a an and are as at be by for from how in into is it its like of on or that the their this to was what when where which who why with you your we our does do can'.split(' '));

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.end(JSON.stringify(body));
}

function tokens(text) {
  return (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter((t) => t.length > 2 && !STOPWORDS.has(t));
}

function retrieve(message, k = 3) {
  const q = tokens(message);
  if (q.length === 0) return [];
  const qset = new Set(q);
  const scored = corpus.map((c) => {
    const ct = tokens(c.text);
    let overlap = 0;
    for (const t of ct) if (qset.has(t)) overlap += 1;
    const score = overlap / Math.sqrt(ct.length || 1);
    return { ...c, score };
  });
  return scored.filter((c) => c.score > 0).sort((a, b) => b.score - a.score).slice(0, k);
}

function firstSentences(text, n = 2) {
  const parts = text.match(/[^.!?]+[.!?]+/g) || [text];
  return parts.slice(0, n).map((s) => s.trim()).join(' ').replace(/\s+/g, ' ').trim();
}

function deterministicAnswer(message, hits) {
  if (hits.length === 0) {
    return "I can only answer questions about the lessons in this library — try asking about hyperconverged infrastructure, virtualization, the hypervisor, or the management plane.";
  }
  const top = hits[0];
  const body = firstSentences(top.text, 3);
  return `${body}\n\n[Video: ${top.title}]`;
}

async function groqAnswer(message, hits) {
  const key = process.env.GROQ_API_KEY;
  if (!key || hits.length === 0) return null;
  const context = hits.map((h, i) => `Source ${i + 1} (from "${h.title}"): ${h.text}`).join('\n\n');
  const body = {
    model: process.env.GROQ_MODEL || 'llama-3.1-8b-instant',
    temperature: 0.6,
    max_tokens: 400,
    messages: [
      { role: 'system', content: 'You are NuggetBot, a warm learning companion. Answer ONLY from the provided sources, in plain language with a friendly analogy when helpful. Keep it to a short paragraph. If the sources do not cover it, say so.' },
      { role: 'user', content: `Question: ${message}\n\nSources:\n${context}` },
    ],
  };
  try {
    const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
      body: JSON.stringify(body),
    });
    if (!r.ok) return null;
    const data = await r.json();
    return data.choices?.[0]?.message?.content?.trim() || null;
  } catch {
    return null;
  }
}

function readBody(req) {
  return new Promise((resolve) => {
    if (req.body !== undefined) {
      resolve(typeof req.body === 'string' ? safeParse(req.body) : req.body);
      return;
    }
    let raw = '';
    req.on('data', (c) => (raw += c));
    req.on('end', () => resolve(safeParse(raw)));
    req.on('error', () => resolve({}));
  });
}

function safeParse(s) {
  try { return s ? JSON.parse(s) : {}; } catch { return {}; }
}

function randomId() {
  return Math.random().toString(16).slice(2, 18);
}

module.exports = async (req, res) => {
  // The vercel.json rewrite maps /api/(.*) -> /api/index?p=$1, so the matched
  // route lives in the `p` query param. Fall back to the raw pathname for
  // direct invocations (e.g. local tests).
  const parsed = new URL(req.url || '/', 'http://localhost');
  const p = parsed.searchParams.get('p');
  let path = p !== null ? `/api/${p}` : parsed.pathname;
  path = path.replace(/\/+$/, '') || '/';
  if (!path.startsWith('/api')) path = `/api${path === '/' ? '' : path}`;
  const method = req.method || 'GET';

  if (method === 'OPTIONS') return send(res, 204, {});

  if (path === '/api/health') {
    return send(res, 200, { status: 'healthy', service: 'video-nuggets-os', mode: 'vercel-static-demo', llm_provider: process.env.GROQ_API_KEY ? 'groq' : 'deterministic', demo_mode: true });
  }

  if (path === '/api/videos' && method === 'GET') {
    return send(res, 200, library);
  }

  if (path === '/api/playlists' && method === 'GET') {
    return send(res, 200, {
      playlists: library.playlists.map((p) => ({ id: p.id, name: p.name, description: p.description, is_default: p.is_default })),
    });
  }

  const detail = path.match(/^\/api\/videos\/(\d+)$/);
  if (detail && method === 'GET') {
    const v = videos[detail[1]];
    return v ? send(res, 200, v) : send(res, 404, { detail: 'Video not found' });
  }

  const download = path.match(/^\/api\/videos\/(\d+)\/download$/);
  if (download && method === 'GET') {
    const v = videos[download[1]];
    if (!v) return send(res, 404, { detail: 'Video not found' });
    res.statusCode = 302;
    res.setHeader('Location', v.video_url);
    return res.end();
  }

  if (path === '/api/chat' && method === 'POST') {
    const body = await readBody(req);
    const message = (body.message || '').toString();
    if (!message.trim()) return send(res, 400, { detail: 'message is required' });
    const hits = retrieve(message);
    const answer = (await groqAnswer(message, hits)) || deterministicAnswer(message, hits);
    const cited = [];
    const seen = new Set();
    for (const h of hits) {
      if (seen.has(h.video_id)) continue;
      seen.add(h.video_id);
      cited.push({ video_id: h.video_id, title: h.title, relevance: Number(h.score.toFixed(3)) });
    }
    return send(res, 200, {
      response: answer,
      session_id: (body.session_id || randomId()).toString(),
      cited_videos: cited,
      suggestions: [
        'How does distributed storage work?',
        'Explain a hypervisor like I\u2019m five',
        'What does the management plane do?',
      ],
    });
  }

  if (path === '/api/auth/login' && method === 'POST') {
    const body = await readBody(req);
    const entry = DEMO_USERS[(body.username || '').toString().toLowerCase()];
    if (!entry || entry.password !== (body.password || '').toString()) {
      return send(res, 401, { detail: 'Invalid username or password' });
    }
    const token = Buffer.from(JSON.stringify(entry.user)).toString('base64');
    return send(res, 200, { access_token: token, token_type: 'bearer', user: entry.user });
  }

  if (path === '/api/auth/me' && method === 'GET') {
    const auth = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    try {
      const user = JSON.parse(Buffer.from(auth, 'base64').toString('utf-8'));
      if (user && user.username) return send(res, 200, user);
    } catch { /* fall through */ }
    return send(res, 401, { detail: 'Not authenticated' });
  }

  if (path.startsWith('/api/uploads') && method === 'POST') {
    return send(res, 503, { detail: 'Live generation runs on the full FastAPI backend (the backend/ folder), not in this cloud demo. Clone the repo and run it locally to generate new nuggets from your own documents.' });
  }

  if (path === '/api/playlists' && method === 'POST') {
    return send(res, 503, { detail: 'Creating playlists requires the full backend (backend/). This cloud demo serves a fixed, pre-rendered library.' });
  }

  if (path === '/api/monitor/runs' && method === 'GET') {
    return send(res, 200, { runs: [], latest: null, pdf_baseline_available: false });
  }

  if (path.startsWith('/api/monitor')) {
    return send(res, 200, { enabled: false, detail: 'The content monitor is an optional agent in the full backend; it is disabled in this cloud demo.', runs: [] });
  }

  return send(res, 404, { detail: `No route for ${method} ${path}` });
};
