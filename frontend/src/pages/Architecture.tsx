import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api'

const PIPELINE = [
  { n: 1, title: 'Parse', svc: 'content_parser.py', desc: 'PDF / PPTX / TXT / image (OCR) / URL → clean, narration-sized sections.' },
  { n: 2, title: 'Simplify', svc: 'content_simplifier.py', desc: 'Rewrite each section "explain-like-I\'m-6" with analogies — Groq Llama-3, or a deterministic fallback.' },
  { n: 3, title: 'Visualize', svc: 'visualization_gen.py', desc: 'Pick a comparison / architecture / flow / key-points chart per section (matplotlib).' },
  { n: 4, title: 'Slides', svc: 'slide_image_generator.py', desc: '1920×1080 branded frames + an animated storyboard engine.' },
  { n: 5, title: 'Narrate', svc: 'tts_service.py', desc: 'Microsoft Edge neural TTS with per-word caption timelines.' },
  { n: 6, title: 'Compose', svc: 'video_composer.py', desc: 'ffmpeg muxes frames + audio into a 1080p MP4 + VTT transcript + thumbnail.' },
  { n: 7, title: 'Index', svc: 'chatbot/embedder.py', desc: 'Chunk + embed into ChromaDB so NuggetBot can answer from the content.' },
]

const STACK: { group: string; items: string[] }[] = [
  { group: 'Frontend', items: ['React 18', 'Vite', 'TypeScript', 'Tailwind CSS', 'React Router'] },
  { group: 'Backend', items: ['FastAPI', 'Python 3.11', 'SQLAlchemy', 'APScheduler', 'Uvicorn'] },
  { group: 'Media pipeline', items: ['ffmpeg', 'Edge TTS', 'Pillow (PIL)', 'matplotlib', 'python-pptx'] },
  { group: 'AI / retrieval', items: ['Groq Llama-3', 'Deterministic fallback', 'ChromaDB', 'MiniLM embeddings'] },
  { group: 'Data', items: ['SQLite', 'ChromaDB vector store', 'Static MP4 / VTT'] },
  { group: 'Infra (this demo)', items: ['Vercel static hosting', 'Vercel serverless function', 'Pre-rendered seed library', 'Docker (full backend, local)'] },
]

interface Health { llm_provider?: string; demo_mode?: boolean; status?: string }

export default function Architecture() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <header className="mb-10">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
          Architecture
        </h1>
        <p className="text-gray-400 mt-2 max-w-3xl">
          Video Nuggets OS is a real full-stack app. The complete
          document-to-video pipeline below is a Dockerized FastAPI backend
          (<code className="text-brand-teal">backend/</code>) that renders with
          ffmpeg + Edge TTS and serves a ChromaDB RAG chatbot — runnable locally.
          This live demo runs entirely on Vercel: a static React app, a
          pre-rendered seed library served as static assets, and one serverless
          function that backs the library and the grounded chatbot.
        </p>
        {health && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="px-3 py-1 rounded-full bg-brand-teal/10 text-brand-teal border border-brand-teal/30">
              backend: {health.status || 'unknown'}
            </span>
            <span className="px-3 py-1 rounded-full bg-brand-purple-light/10 text-brand-purple-light border border-brand-purple-light/30">
              LLM: {health.llm_provider || 'deterministic'}
            </span>
            {health.demo_mode && (
              <span className="px-3 py-1 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30">
                demo mode
              </span>
            )}
          </div>
        )}
      </header>

      {/* Deployment diagram */}
      <section className="mb-12">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Deployed topology (this demo)</h2>
        <div className="grid md:grid-cols-3 gap-4">
          <Box title="Static app · Vercel" tone="purple"
            lines={['React + Vite + Tailwind', 'Library · Watch · Chat', 'Architecture · Upload', 'served from the CDN']} />
          <Box title="Serverless · Vercel function" tone="teal"
            lines={['/api/videos · /api/chat', 'grounded retrieval', 'Groq Llama-3 (if keyed)', 'deterministic fallback']} />
          <Box title="Seed library (static)" tone="green"
            lines={['3 pre-rendered MP4s', 'VTT transcripts', 'thumbnails', 'served from /static']} />
        </div>
        <p className="text-xs text-gray-500 mt-3">
          Request flow: Browser → Vercel static app → <code className="text-brand-teal">/api/*</code> serverless function (library + grounded chat) and <code className="text-brand-teal">/static/*</code> for the pre-rendered MP4s. The full ffmpeg/Edge-TTS pipeline below runs in the local <code className="text-brand-teal">backend/</code> to produce that seed library.
        </p>
      </section>

      {/* Pipeline */}
      <section className="mb-12">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">The generation pipeline</h2>
        <div className="space-y-3">
          {PIPELINE.map((p, i) => (
            <div key={p.n} className="flex items-stretch gap-3">
              <div className="flex flex-col items-center">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brand-purple-light to-brand-teal text-white font-bold flex items-center justify-center text-sm">
                  {p.n}
                </div>
                {i < PIPELINE.length - 1 && <div className="flex-1 w-px bg-gray-700 my-1" />}
              </div>
              <div className="flex-1 bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-3 mb-1">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <h3 className="font-semibold text-gray-100">{p.title}</h3>
                  <code className="text-[11px] text-brand-teal">{p.svc}</code>
                </div>
                <p className="text-sm text-gray-400 mt-1">{p.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Stack */}
      <section className="mb-12">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Tech stack</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {STACK.map((s) => (
            <div key={s.group} className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-brand-purple-light mb-2">{s.group}</h3>
              <div className="flex flex-wrap gap-1.5">
                {s.items.map((it) => (
                  <span key={it} className="text-xs px-2 py-1 rounded-md bg-gray-900 border border-gray-700 text-gray-300">
                    {it}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="text-xs text-gray-500 border-t border-gray-800 pt-6">
        <p className="mb-2">
          The "simplify" step and NuggetBot use a free Groq Llama-3 key when configured, and a deterministic, zero-cost fallback otherwise — so the demo always works.
        </p>
        <p>
          Independent, original prototype. Not affiliated with or endorsed by Nutanix, Inc. The sample documents are original and vendor-neutral.
        </p>
      </section>
    </div>
  )
}

function Box({ title, lines, tone }: { title: string; lines: string[]; tone: 'purple' | 'teal' | 'green' }) {
  const ring = tone === 'purple' ? 'border-brand-purple-light/40' : tone === 'teal' ? 'border-brand-teal/40' : 'border-brand-green/40'
  const head = tone === 'purple' ? 'text-brand-purple-light' : tone === 'teal' ? 'text-brand-teal' : 'text-brand-green'
  return (
    <div className={`bg-gray-800/50 border ${ring} rounded-xl p-4`}>
      <h3 className={`font-semibold ${head} mb-2`}>{title}</h3>
      <ul className="space-y-1 text-sm text-gray-300">
        {lines.map((l) => <li key={l}>· {l}</li>)}
      </ul>
    </div>
  )
}
