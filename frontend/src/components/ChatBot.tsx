import { useState, useRef, useEffect } from 'react'
import ChatMessage from './ChatMessage'
import ChatSuggestions from './ChatSuggestions'
import { API_BASE } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  cited_videos?: { video_id: number; title: string }[]
}

interface ChatBotProps {
  compact?: boolean
}

export default function ChatBot({ compact = false }: ChatBotProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([
    'What is hyperconverged infrastructure?',
    'How does distributed storage work?',
    'Explain a hypervisor like I\'m five',
  ])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text: string) => {
    if (!text.trim()) return

    const userMessage: Message = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(`${API_BASE}/api/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      })
      const data = await response.json()

      const assistantMessage: Message = {
        role: 'assistant',
        content: data.response,
        cited_videos: data.cited_videos,
      }
      setMessages((prev) => [...prev, assistantMessage])
      setSessionId(data.session_id)
      if (data.suggestions?.length) {
        setSuggestions(data.suggestions)
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Oops! Something went wrong. Try again in a moment.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sendMessage(input)
  }

  const containerClass = compact
    ? 'flex flex-col h-full'
    : 'flex flex-col h-[calc(100vh-5rem)] max-w-4xl mx-auto'

  return (
    <div className={containerClass}>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-gradient-to-br from-brand-purple-light to-brand-teal flex items-center justify-center">
              <span className="text-white font-bold text-xl">N</span>
            </div>
            <h2 className="text-lg font-semibold text-gray-200 mb-2">Hi, I'm NuggetBot</h2>
            <p className="text-gray-400 text-sm max-w-md mx-auto px-4">
              I answer questions about the video lessons in this library —
              grounded in the generated content and citing the source nugget.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}

        {loading && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-purple-light to-brand-teal flex items-center justify-center flex-shrink-0">
              <span className="text-white font-bold text-xs">N</span>
            </div>
            <div className="bg-gray-900 rounded-xl px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 rounded-full bg-brand-teal animate-bounce [animation-delay:0ms]" />
                <div className="w-2 h-2 rounded-full bg-brand-teal animate-bounce [animation-delay:150ms]" />
                <div className="w-2 h-2 rounded-full bg-brand-teal animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {messages.length === 0 && (
        <ChatSuggestions suggestions={suggestions} onSelect={sendMessage} />
      )}

      <form onSubmit={handleSubmit} className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask NuggetBot about the lessons..."
            className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="btn-primary px-6 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
            </svg>
          </button>
        </div>
      </form>
    </div>
  )
}
