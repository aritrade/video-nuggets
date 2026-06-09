import { Link } from 'react-router-dom'

interface MessageProps {
  message: {
    role: 'user' | 'assistant'
    content: string
    cited_videos?: { video_id: number; title: string }[]
  }
}

export default function ChatMessage({ message }: MessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
        isUser
          ? 'bg-brand-dark-blue'
          : 'bg-gradient-to-br from-brand-purple-light to-brand-teal'
      }`}>
        <span className="text-sm">{isUser ? '👤' : '🤖'}</span>
      </div>

      <div className={`max-w-[75%] ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block rounded-xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-brand-purple-light text-white'
            : 'bg-gray-900 text-gray-200 border border-gray-800'
        }`}>
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>

        {message.cited_videos && message.cited_videos.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.cited_videos.map((video, i) => (
              video.video_id && (
                <Link
                  key={i}
                  to={`/watch/${video.video_id}`}
                  className="inline-flex items-center gap-1 text-xs bg-brand-teal/10 text-brand-teal px-2 py-1 rounded-full hover:bg-brand-teal/20 transition-colors"
                >
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z"/>
                  </svg>
                  {video.title}
                </Link>
              )
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
