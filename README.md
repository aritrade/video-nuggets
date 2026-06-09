# Video Nuggets OS

**Turn any document into a narrated, auto-advancing micro-lesson — with charts, captions, and a Q&A bot — entirely in your browser.**

![status](https://img.shields.io/badge/status-live%20prototype-7c5cff)
![stack](https://img.shields.io/badge/stack-vanilla%20JS%20%C2%B7%20zero%20backend-23c4d6)
![hosting](https://img.shields.io/badge/hosting-static%20%C2%B7%20Vercel%20%2F%20Pages-green)
![cost](https://img.shields.io/badge/cost-%240%20%C2%B7%20no%20API%20key%20needed-success)
![license](https://img.shields.io/badge/license-All%20Rights%20Reserved-red)

Video Nuggets OS is a **public, in-browser prototype** that replicates the concept
of a larger doc-to-video platform I built. Paste a document, and it runs a full
pipeline — **parse → simplify → visualize → slides → narrate → play** — then
hands you a short "nugget" lesson you can watch, scrub, and *ask questions
about*. No upload, no server, no API key. Everything happens on your device.

---

## Why I built this

Good documentation is everywhere; the *patience* to read it isn't. I kept
watching capable people bounce off dense infrastructure docs that would have
made perfect sense as a friendly five-minute video. So I built a pipeline that
takes the document you already have and turns it into the lesson you'd actually
watch — explained in plain language, with a visual per idea and a voice reading
it to you.

The production version is a Python/FastAPI service with a heavyweight render
stack (local LLM via Ollama, Microsoft Edge TTS, ffmpeg, LibreOffice, a
ChromaDB vector store). That's great for batch-producing real 1080p MP4s — and
terrible for "let me just try it." **This repo is the opposite trade-off:** the
same conceptual pipeline, re-expressed with zero-cost browser primitives so it
loads instantly and runs anywhere, while staying honest about what each stage
maps to in the real system.

---

## Try it

1. Open the live site (or `index.html` locally).
2. Click a **sample document**, or paste your own (short heading lines help it
   find sections).
3. Hit **Make the nugget** and watch the pipeline stages light up.
4. Press **Play** — the lesson narrates and auto-advances. Toggle captions,
   change speed, jump around via the transcript, or go fullscreen.
5. Ask **NuggetBot** a question — it answers only from the generated lesson and
   cites the slide it came from.

> Narration uses your browser's built-in speech engine (the Web Speech API), so
> the available voice depends on your OS/browser. Chrome, Edge, and Safari work
> well.

---

## How it works — and how it maps to the production backend

Every stage here is a faithful, lightweight stand-in for a real backend
service. The concept is identical; only the implementation is browser-native.

| Stage | This prototype (browser) | Production backend (Python) |
| --- | --- | --- |
| **Parse** | Heading detection + section consolidation in JS | `content_parser.py` — PDF / PPTX / TXT / image (OCR) / URL |
| **Simplify** | Deterministic "explain-like-I'm-6" rewriter with an analogy glossary; optional BYO-LLM hook | `content_simplifier.py` — Google Gemma via Ollama |
| **Visualize** | Inline SVG charts/diagrams chosen by keyword heuristics | `visualization_gen.py` — matplotlib/plotly |
| **Slides** | Slide objects (intro / content + viz / outro) | `slide_generator.py` — branded PPTX layouts |
| **Narrate** | Web Speech API, per-slide | `tts_service.py` — Edge TTS + word-level timelines |
| **Compose** | Auto-advancing narrated player | `video_composer.py` — ffmpeg → 1080p MP4 |
| **Q&A** | In-browser TF-IDF index + cosine retrieval (NuggetBot) | `rag_engine.py` + ChromaDB + MiniLM embeddings |

### The simplifier (the interesting bit)

The hardest stage to make free *and* useful is "rewrite this so a six-year-old
gets it." The backend asks a local LLM. Here, the default is a **deterministic
simplifier**: it splits the section into sentences, matches jargon against an
analogy glossary (`cluster → "a team of friends sharing toys"`,
`hypervisor → "a careful babysitter for pretend computers"`, …), softens
connective jargon, and budgets to ~90 narration words per slide — the same
budget the backend prompt targets.

It will never be as fluent as an LLM, and that's the point: the demo **always
works, at zero cost, with nothing installed**. If you want the LLM path, flip
the toggle and paste any OpenAI-compatible endpoint + key — it's used
client-side only and never stored. This mirrors how my
[risk-analyzer demo](https://github.com/aritrade/enterprise-adoption-risk-analyzer)
treats Claude: real integration, graceful zero-cost fallback.

---

## Architecture

```
                ┌───────────────────────────────────────────────┐
  Document ───▶ │  index.html  (UI · player · chat)             │
  (sample/      └───────────────┬───────────────────────────────┘
   paste)                       │
                                ▼
                   assets/js/pipeline.js  (window.VN)
        parse() → simplify() → visualize() → buildSlides() → buildIndex()
                                │                     │
                                ▼                     ▼
                   assets/js/app.js            NuggetBot (ask())
        narrated player · transcript · controls · TF-IDF retrieval
```

No build step, no dependencies, no network calls (unless you opt into your own
LLM). It's three scripts and a stylesheet.

---

## Project structure

```
video-nuggets/
├── index.html              # UI: input, pipeline, player, chat, about
├── assets/
│   ├── css/style.css        # all styling
│   └── js/
│       ├── samples.js       # original, vendor-neutral sample documents
│       ├── pipeline.js      # parse · simplify · visualize · slides · TF-IDF
│       └── app.js           # orchestration · narrated player · NuggetBot UI
├── vercel.json
├── LICENSE
└── README.md
```

---

## Deploy (free)

It's a static site, so any static host works.

**Vercel**
```sh
npm i -g vercel
vercel --prod
```

**GitHub Pages** — push the repo, then enable Pages on the `main` branch
(root). No configuration needed.

**Locally**
```sh
python3 -m http.server 8080
# open http://localhost:8080
```

---

## Project phases

How this prototype came together:

- **Phase 1 — Parser.** Heading detection + section consolidation so messy text becomes clean, narration-sized chunks.
- **Phase 2 — Simplifier.** Deterministic analogy engine with a jargon glossary and a word budget; optional BYO-LLM hook behind the same interface.
- **Phase 3 — Visualizer.** Keyword-driven selection of inline SVG comparison / architecture / flow / key-point visuals — no chart library.
- **Phase 4 — Slides + player.** Intro/content/outro slide model and an auto-advancing, narrated player (Web Speech API) with transcript, speed, captions, and fullscreen.
- **Phase 5 — NuggetBot.** A tiny TF-IDF + cosine retriever over the generated lesson that answers only from content and cites its source slide.
- **Phase 6 — Polish & ship.** Staged pipeline visualization, responsive UI, original sample docs, and a static-first deploy story.

### Roadmap — what's next

- **Real MP4 export** in-browser via `MediaRecorder` (canvas + `SpeechSynthesis` capture) so a nugget can be downloaded, not just played.
- **Word-level caption highlighting** using `SpeechSynthesis` boundary events (the backend already emits Edge TTS timelines for this).
- **PDF / URL ingestion** client-side (pdf.js + a CORS-friendly reader) to match the backend's parser coverage.
- **Embeddings upgrade** — swap TF-IDF for a small in-browser embedding model (e.g. via `transformers.js`) for semantic Q&A.
- **Pluggable themes** so the same pipeline can render in any brand's palette.

---

## License & disclaimer

**All Rights Reserved** — see [`LICENSE`](LICENSE). Published for portfolio
review and evaluation only.

This is an **independent, original prototype**. It is **not affiliated with,
endorsed by, or associated with Nutanix, Inc.** "Nutanix" and the "Nutanix
Bible" are referenced only as examples of the kind of publicly available
document this tool is designed for. **No Nutanix trademarks, brand assets,
slide templates, validated designs, or proprietary materials are included** in
this repository. All sample texts are original and vendor-neutral.
