/*
 * Video Nuggets OS — in-browser pipeline.
 *
 * This file is the public, client-side conceptual replica of the production
 * pipeline (Python/FastAPI). Each module here maps 1:1 to a backend service:
 *
 *   parse()      ->  content_parser.parse_source()
 *   simplify()   ->  content_simplifier.simplify_content()  (Gemma via Ollama)
 *   visualize()  ->  visualization_gen.*  (matplotlib charts/diagrams)
 *   buildSlides()->  slide_generator.generate_slides()
 *   (narration)  ->  tts_service.generate_narration()  (Edge TTS + timelines)
 *   (compose)    ->  video_composer.compose_video()  (ffmpeg -> 1080p MP4)
 *   NuggetBot    ->  chatbot/rag_engine + embedder (ChromaDB + MiniLM)
 *
 * In the browser we trade heavyweight, server-side tools (Ollama, ffmpeg,
 * LibreOffice, ChromaDB) for their zero-cost web equivalents: a deterministic
 * simplifier (with an optional BYO-LLM hook), SVG visuals, the Web Speech API
 * for narration, an auto-advancing slide player in place of an MP4, and a tiny
 * TF-IDF index in place of a vector store. Same concept, nothing to install.
 */
(function () {
  "use strict";

  const VN = (window.VN = window.VN || {});

  // ──────────────────────────────────────────────────────────────────────
  // 1. PARSER  (mirrors content_parser.py)
  // ──────────────────────────────────────────────────────────────────────

  const MIN_BODY_CHARS = 220;
  const MAX_SECTIONS = 8;

  function makeKey(title) {
    return (title || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .slice(0, 80)
      .replace(/^_+|_+$/g, "");
  }

  function isHeading(line) {
    const l = line.trim();
    if (l.length > 80 || l.length < 4) return false;
    if (/^(#{1,3}\s+|chapter\s+\d+|section\s+\d+|part\s+[ivx0-9]+)\b/i.test(l)) return true;
    if (/^\d+(\.\d+){0,2}\s+[A-Z][A-Za-z]/.test(l)) return true;
    // Title-case-ish line with no sentence-terminal punctuation = likely a
    // heading. A trailing "?" is allowed because questions are common titles.
    const endsClean = !/[.,;:!]$/.test(l);
    const words = l.split(/\s+/);
    if (endsClean && words.length >= 2 && words.length <= 12) {
      const caps = words.filter((w) => /^[A-Z]/.test(w)).length;
      if (caps / words.length >= 0.5) return true;
    }
    return false;
  }

  function consolidate(sections) {
    if (!sections.length) return sections;
    const merged = [];
    let pending = null;
    for (let sec of sections) {
      if (pending) {
        sec = {
          title: pending.title || sec.title,
          body: (pending.body + "\n\n" + (sec.title ? sec.title + "\n" : "") + sec.body).trim(),
          key: pending.key || sec.key,
        };
        pending = null;
      }
      if (sec.body.trim().length < MIN_BODY_CHARS) {
        pending = sec;
        continue;
      }
      merged.push(sec);
    }
    if (pending) {
      if (merged.length) {
        const tail = merged[merged.length - 1];
        tail.body = (tail.body + "\n\n" + (pending.title ? pending.title + "\n" : "") + pending.body).trim();
      } else {
        merged.push(pending);
      }
    }
    while (merged.length > MAX_SECTIONS) {
      let shortest = 0;
      let best = Infinity;
      for (let i = 0; i < merged.length - 1; i++) {
        const len = merged[i].body.length + merged[i + 1].body.length;
        if (len < best) {
          best = len;
          shortest = i;
        }
      }
      const a = merged[shortest];
      const b = merged[shortest + 1];
      a.body = (a.body + "\n\n" + (b.title ? b.title + "\n" : "") + b.body).trim();
      merged.splice(shortest + 1, 1);
    }
    return merged;
  }

  VN.parse = function parse(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    const sections = [];
    let curTitle = "";
    let curBody = [];
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      if (isHeading(line)) {
        if (curTitle || curBody.length) {
          sections.push({
            title: curTitle || "Introduction",
            body: curBody.join("\n"),
            key: makeKey(curTitle),
          });
        }
        curTitle = line.replace(/^#{1,3}\s+/, "");
        curBody = [];
      } else {
        curBody.push(line);
      }
    }
    if (curTitle || curBody.length) {
      sections.push({ title: curTitle || "Content", body: curBody.join("\n"), key: makeKey(curTitle) });
    }
    const title = sections.length ? sections[0].title : "Untitled";
    return { title, sections: consolidate(sections), sourceType: "text", rawText: text };
  };

  // ──────────────────────────────────────────────────────────────────────
  // 2. SIMPLIFIER  (mirrors content_simplifier.py — Gemma "explain to a 6yo")
  //    Deterministic by default; optional BYO-LLM hook (OpenAI-compatible).
  // ──────────────────────────────────────────────────────────────────────

  // Plain-language analogies for common infrastructure jargon. The backend
  // asks Gemma to do this; here we do it transparently and for free.
  const ANALOGIES = [
    [/\bhyperconverged infrastructure\b|\bHCI\b/i, "one all-in-one box that does both the thinking and the remembering, instead of lots of separate boxes"],
    [/\bclusters?\b/i, "a team of friends who share their toys so they can do bigger things together"],
    [/\bnodes?\b/i, "a single building block, like one LEGO brick you can keep adding more of"],
    [/\bhypervisor\b/i, "a careful babysitter that lets many pretend-computers share one real computer without fighting"],
    [/\bvirtual machines?\b|\bVMs?\b/i, "a pretend computer that lives inside a real one"],
    [/\bdistributed storage\b|\bstorage pool\b/i, "a giant shared toy box that every computer can reach into"],
    [/\bAPI\b/i, "a doorway that lets one program politely ask another program to do something"],
    [/\bscale-out\b|\bscale out\b/i, "growing by adding more building blocks instead of buying one giant thing"],
    [/\bredundan\w*\b|\breplicat\w*\b/i, "keeping more than one copy, so losing one is no big deal"],
    [/\bself-healing\b|\brebuilds?\b/i, "fixing itself quietly in the background, like a cut that scabs over on its own"],
    [/\bmanagement plane\b|\bconsole\b/i, "a control tower where one person can see and steer everything at once"],
    [/\bscheduler\b/i, "a fair teacher who decides whose turn it is so nobody is left out or overloaded"],
  ];

  function splitSentences(text) {
    return text
      .replace(/\n+/g, " ")
      .split(/(?<=[.!?])\s+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function pickAnalogy(text) {
    for (const [re, phrase] of ANALOGIES) {
      const m = text.match(re);
      if (m) return { term: m[0], phrase };
    }
    return null;
  }

  function deterministicSimplify(section) {
    const sentences = splitSentences(section.body);
    const lead = sentences.slice(0, 3).join(" ");
    const analogy = pickAnalogy(section.title + " " + section.body);

    let out = [];
    const topic = section.title.toLowerCase().replace(/[.:?!]+$/, "").trim();
    out.push(`Let's talk about ${topic}.`);
    if (analogy) {
      out.push(`Think of ${analogy.term} like ${analogy.phrase}.`);
    }
    // Gently simplify the lead text: soften connective jargon, keep facts.
    let simple = lead
      .replace(/\butiliz(e|es|ing|ation)\b/gi, "use")
      .replace(/\bleverag(e|es|ing)\b/gi, "use")
      .replace(/\bin order to\b/gi, "to")
      .replace(/\bsubsequently\b/gi, "then")
      .replace(/\bapproximately\b/gi, "about");
    if (simple) out.push(simple);
    out.push("And that's the big idea — simple building blocks working together.");

    let narration = out.join(" ").replace(/\s+/g, " ").trim();
    // Target ~90 words like the backend's per-slide budget.
    const words = narration.split(/\s+/);
    if (words.length > 95) narration = words.slice(0, 95).join(" ") + " …";
    return narration;
  }

  // Optional: route through a user-supplied OpenAI-compatible chat endpoint.
  async function llmSimplify(section, cfg) {
    const prompt =
      `Rewrite this so a 6-year-old understands it, using a real-world analogy, ` +
      `keeping facts accurate, ~80 words, narration-ready, no headers.\n\n` +
      `TITLE: ${section.title}\n\nCONTENT:\n${section.body}`;
    const resp = await fetch(cfg.endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${cfg.apiKey}` },
      body: JSON.stringify({
        model: cfg.model || "gpt-4o-mini",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.7,
        max_tokens: 300,
      }),
    });
    if (!resp.ok) throw new Error("LLM " + resp.status);
    const data = await resp.json();
    return (data.choices?.[0]?.message?.content || "").trim();
  }

  VN.simplify = async function simplify(parsed, opts) {
    opts = opts || {};
    const llm = opts.llm; // {endpoint, apiKey, model} or undefined
    const sections = [];
    let usedLLM = false;
    for (const sec of parsed.sections) {
      let narration;
      if (llm && llm.endpoint && llm.apiKey) {
        try {
          narration = await llmSimplify(sec, llm);
          usedLLM = true;
        } catch (e) {
          narration = deterministicSimplify(sec);
        }
      } else {
        narration = deterministicSimplify(sec);
      }
      sections.push({ ...sec, narration });
    }
    return { ...parsed, sections, simplifiedBy: usedLLM ? "llm" : "deterministic" };
  };

  // ──────────────────────────────────────────────────────────────────────
  // 3. VISUALIZER  (mirrors visualization_gen.py — chart/diagram per section)
  //    Renders inline SVG so it needs no chart library.
  // ──────────────────────────────────────────────────────────────────────

  const C = {
    bg: "#0e1726", panel: "#16213a", line: "#27406b",
    a: "#7c5cff", b: "#23c4d6", c: "#3ddc84", warn: "#ffb454", text: "#e8edf6", muted: "#9fb0cc",
  };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function svgBars(title) {
    const cats = ["Complexity", "Scale", "Management", "Cost"];
    const trad = [8, 4, 9, 8];
    const ours = [3, 9, 2, 4];
    const w = 760, h = 380, pad = 70, bw = 46, gap = 24;
    let bars = "";
    cats.forEach((cat, i) => {
      const x = pad + i * (bw * 2 + gap + 28);
      const ht = (v) => (v / 10) * (h - pad - 60);
      bars += `<rect x="${x}" y="${h - 50 - ht(trad[i])}" width="${bw}" height="${ht(trad[i])}" rx="6" fill="${C.warn}"/>`;
      bars += `<rect x="${x + bw + 8}" y="${h - 50 - ht(ours[i])}" width="${bw}" height="${ht(ours[i])}" rx="6" fill="${C.a}"/>`;
      bars += `<text x="${x + bw}" y="${h - 28}" fill="${C.muted}" font-size="14" text-anchor="middle">${esc(cat)}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" class="viz">
      <text x="${pad}" y="40" fill="${C.text}" font-size="22" font-weight="700">${esc(title)}</text>
      <g transform="translate(${w - 230},26)">
        <rect width="14" height="14" rx="3" fill="${C.warn}"/><text x="20" y="12" fill="${C.muted}" font-size="13">Traditional</text>
        <rect y="22" width="14" height="14" rx="3" fill="${C.a}"/><text x="20" y="34" fill="${C.muted}" font-size="13">Hyperconverged</text>
      </g>${bars}</svg>`;
  }

  function svgLayers(title) {
    const layers = [
      ["Applications", "VMs · Containers · Databases", C.a],
      ["Platform Services", "Files · Objects · Volumes", C.b],
      ["Core", "Storage · Compute · Network", C.c],
      ["Infrastructure", "Hardware · Hypervisor", C.muted],
    ];
    const w = 760, h = 380, x = 110, lw = 540, lh = 64, gap = 14;
    let g = "";
    layers.forEach((L, i) => {
      const y = 70 + i * (lh + gap);
      g += `<rect x="${x}" y="${y}" width="${lw}" height="${lh}" rx="12" fill="${C.panel}" stroke="${L[2]}" stroke-width="2"/>
        <text x="${x + 22}" y="${y + 28}" fill="${C.text}" font-size="18" font-weight="700">${esc(L[0])}</text>
        <text x="${x + 22}" y="${y + 50}" fill="${C.muted}" font-size="13">${esc(L[1])}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" class="viz">
      <text x="${x}" y="44" fill="${C.text}" font-size="22" font-weight="700">${esc(title)}</text>${g}</svg>`;
  }

  function svgFlow(title, steps) {
    const w = 760, h = 300;
    const n = Math.min(steps.length, 5);
    const bw = (w - 80 - (n - 1) * 36) / n;
    let g = "";
    for (let i = 0; i < n; i++) {
      const x = 40 + i * (bw + 36);
      g += `<rect x="${x}" y="120" width="${bw}" height="84" rx="12" fill="${C.panel}" stroke="${C.b}" stroke-width="2"/>
        <text x="${x + bw / 2}" y="150" fill="${C.b}" font-size="20" font-weight="800" text-anchor="middle">${i + 1}</text>
        <text x="${x + bw / 2}" y="178" fill="${C.text}" font-size="12" text-anchor="middle">${esc((steps[i] || "").slice(0, 22))}</text>`;
      if (i < n - 1) g += `<text x="${x + bw + 12}" y="170" fill="${C.a}" font-size="26" text-anchor="middle">→</text>`;
    }
    return `<svg viewBox="0 0 ${w} ${h}" class="viz">
      <text x="40" y="60" fill="${C.text}" font-size="22" font-weight="700">${esc(title)}</text>${g}</svg>`;
  }

  function svgPoints(title, points) {
    const w = 760, h = 360, cols = 2;
    let g = "";
    points.slice(0, 4).forEach((p, i) => {
      const x = 60 + (i % cols) * 360;
      const y = 90 + Math.floor(i / cols) * 130;
      g += `<rect x="${x}" y="${y}" width="320" height="100" rx="14" fill="${C.panel}" stroke="${C.line}"/>
        <circle cx="${x + 36}" cy="${y + 50}" r="22" fill="${C.a}"/>
        <text x="${x + 36}" y="${y + 57}" fill="#fff" font-size="20" font-weight="800" text-anchor="middle">${i + 1}</text>
        <text x="${x + 72}" y="${y + 56}" fill="${C.text}" font-size="15">${esc((p || "").slice(0, 28))}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" class="viz">
      <text x="60" y="56" fill="${C.text}" font-size="22" font-weight="700">${esc(title)}</text>${g}</svg>`;
  }

  function extractSteps(text) {
    const lines = text.split(/\n|(?<=[.!?])\s+/);
    const steps = [];
    for (const l of lines) {
      const t = l.trim().replace(/^[-•*]\s*/, "").replace(/^\d+[.)]\s*/, "");
      if (t.length > 6 && t.length < 60) steps.push(t.split(/\s+/).slice(0, 4).join(" "));
      if (steps.length >= 5) break;
    }
    return steps;
  }

  function extractPoints(text) {
    const sents = splitSentences(text);
    return sents.slice(0, 4).map((s) => s.split(/\s+/).slice(0, 5).join(" "));
  }

  VN.visualize = function visualize(section) {
    const body = (section.title + " " + section.body).toLowerCase();
    if (/\b(vs|versus|compared to|traditional|legacy)\b/.test(body)) {
      return { type: "comparison", svg: svgBars(section.title) };
    }
    if (/\b(layer|stack|architecture|platform|plane)\b/.test(body)) {
      return { type: "architecture", svg: svgLayers(section.title) };
    }
    if (/\b(step|process|flow|first|then|finally|migrat|schedul)\b/.test(body)) {
      const steps = extractSteps(section.body);
      if (steps.length >= 3) return { type: "flow", svg: svgFlow(section.title, steps) };
    }
    const pts = extractPoints(section.body);
    return { type: "points", svg: svgPoints(section.title, pts) };
  };

  // ──────────────────────────────────────────────────────────────────────
  // 4. SLIDE BUILDER  (mirrors slide_generator.py)
  // ──────────────────────────────────────────────────────────────────────

  function bulletsFrom(section) {
    const sents = splitSentences(section.body);
    return sents.slice(0, 4).map((s) => {
      const words = s.split(/\s+/);
      return words.slice(0, 10).join(" ") + (words.length > 10 ? "…" : "");
    });
  }

  VN.buildSlides = function buildSlides(simplified) {
    const slides = [];
    slides.push({
      kind: "intro",
      title: simplified.title,
      subtitle: "A Video Nugget",
      narration: `Welcome to Video Nuggets OS. In this short lesson we'll explore ${simplified.title}. Let's get started!`,
    });
    simplified.sections.forEach((sec) => {
      slides.push({
        kind: "content",
        title: sec.title,
        bullets: bulletsFrom(sec),
        viz: VN.visualize(sec),
        narration: sec.narration,
        key: sec.key,
      });
    });
    slides.push({
      kind: "outro",
      title: "That's a wrap!",
      subtitle: simplified.title,
      narration: `That wraps up our nugget on ${simplified.title}. Thanks for watching — explore another doc to make your next Video Nugget!`,
    });
    return slides;
  };

  // ──────────────────────────────────────────────────────────────────────
  // 5. NuggetBot  (mirrors chatbot/rag_engine.py + embedder — TF-IDF here)
  // ──────────────────────────────────────────────────────────────────────

  const STOP = new Set(("the a an of to and or is are be in on for with that this it as at by from your you we our " +
    "they their its can will would could one many each so into out up no not but if then than").split(" "));

  function tokenize(s) {
    return (s.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 2 && !STOP.has(w));
  }

  VN.buildIndex = function buildIndex(simplified) {
    const docs = simplified.sections.map((sec) => ({
      title: sec.title,
      text: sec.body + " " + (sec.narration || ""),
      sentences: splitSentences(sec.body),
      tokens: tokenize(sec.body + " " + (sec.narration || "")),
    }));
    const df = {};
    docs.forEach((d) => {
      new Set(d.tokens).forEach((t) => (df[t] = (df[t] || 0) + 1));
    });
    const N = docs.length || 1;
    const idf = {};
    Object.keys(df).forEach((t) => (idf[t] = Math.log(1 + N / df[t])));
    docs.forEach((d) => {
      const tf = {};
      d.tokens.forEach((t) => (tf[t] = (tf[t] || 0) + 1));
      d.vec = {};
      Object.keys(tf).forEach((t) => (d.vec[t] = (tf[t] / d.tokens.length) * (idf[t] || 0)));
      d.norm = Math.sqrt(Object.values(d.vec).reduce((a, v) => a + v * v, 0)) || 1;
    });
    return { docs, idf };
  };

  function cosine(qvec, qnorm, d) {
    let dot = 0;
    Object.keys(qvec).forEach((t) => {
      if (d.vec[t]) dot += qvec[t] * d.vec[t];
    });
    return dot / (qnorm * d.norm);
  }

  VN.ask = function ask(index, question) {
    const qt = tokenize(question);
    if (!qt.length) return { answer: "Ask me something about the lesson!", sources: [], confidence: 0 };
    const qtf = {};
    qt.forEach((t) => (qtf[t] = (qtf[t] || 0) + 1));
    const qvec = {};
    qt.forEach((t) => (qvec[t] = (qtf[t] / qt.length) * (index.idf[t] || Math.log(2))));
    const qnorm = Math.sqrt(Object.values(qvec).reduce((a, v) => a + v * v, 0)) || 1;

    const scored = index.docs
      .map((d) => ({ d, score: cosine(qvec, qnorm, d) }))
      .sort((a, b) => b.score - a.score);

    const top = scored[0];
    if (!top || top.score < 0.04) {
      return {
        answer: "I couldn't find that in this lesson. Try asking about one of the topics covered in the slides.",
        sources: [],
        confidence: 0,
      };
    }
    // Pick the most query-relevant sentences from the best section.
    const best = top.d;
    const ranked = best.sentences
      .map((s) => {
        const st = tokenize(s);
        const overlap = st.filter((t) => qvec[t]).length;
        return { s, overlap };
      })
      .sort((a, b) => b.overlap - a.overlap)
      .filter((x) => x.overlap > 0)
      .slice(0, 2)
      .map((x) => x.s);
    const answer = ranked.length ? ranked.join(" ") : best.sentences.slice(0, 2).join(" ");
    const sources = scored.filter((x) => x.score > 0.04).slice(0, 3).map((x) => ({ title: x.d.title, score: x.score }));
    return { answer, sources, confidence: top.score };
  };
})();
