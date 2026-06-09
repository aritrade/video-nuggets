import { useState, useEffect, useRef } from 'react'

interface TranscriptEntry {
  start: number
  end: number
  text: string
}

interface TranscriptPanelProps {
  url: string
  currentTime: number
}

export default function TranscriptPanel({ url, currentTime }: TranscriptPanelProps) {
  const [entries, setEntries] = useState<TranscriptEntry[]>([])
  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(url)
      .then((res) => res.text())
      .then((vtt) => {
        const parsed = parseVTT(vtt)
        setEntries(parsed)
      })
      .catch(console.error)
  }, [url])

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [currentTime])

  const activeIndex = entries.findIndex(
    (e) => currentTime >= e.start && currentTime <= e.end
  )

  return (
    <div className="w-full lg:w-80 bg-gray-900 border border-gray-800 rounded-xl p-4 max-h-[500px] overflow-y-auto">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Transcript
      </h3>
      <div className="space-y-2">
        {entries.map((entry, i) => (
          <div
            key={i}
            ref={i === activeIndex ? activeRef : null}
            className={`p-2 rounded-lg text-sm transition-colors ${
              i === activeIndex
                ? 'bg-brand-purple-light/20 text-white border-l-2 border-brand-teal'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <span className="text-xs text-brand-teal mr-2">
              {formatTimestamp(entry.start)}
            </span>
            {entry.text}
          </div>
        ))}
        {entries.length === 0 && (
          <p className="text-gray-500 text-sm">Loading transcript...</p>
        )}
      </div>
    </div>
  )
}

function parseVTT(vtt: string): TranscriptEntry[] {
  const lines = vtt.split('\n')
  const entries: TranscriptEntry[] = []
  let i = 0

  while (i < lines.length) {
    if (lines[i].includes('-->')) {
      const [startStr, endStr] = lines[i].split('-->')
      const start = parseTimestamp(startStr.trim())
      const end = parseTimestamp(endStr.trim())
      i++
      const textLines: string[] = []
      while (i < lines.length && lines[i].trim() !== '') {
        textLines.push(lines[i].trim())
        i++
      }
      entries.push({ start, end, text: textLines.join(' ') })
    }
    i++
  }

  return entries
}

function parseTimestamp(ts: string): number {
  const parts = ts.split(':')
  if (parts.length === 3) {
    const [h, m, s] = parts
    return parseInt(h) * 3600 + parseInt(m) * 60 + parseFloat(s)
  }
  return 0
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
