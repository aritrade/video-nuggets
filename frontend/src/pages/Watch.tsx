import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import VideoPlayer from '../components/VideoPlayer'
import { useAuth } from '../context/AuthContext'
import { API_BASE } from '../lib/api'

interface VideoDetail {
  id: number
  title: string
  description: string
  status: string
  video_url: string | null
  transcript_url: string | null
  slides_url: string | null
  duration_seconds: number | null
  difficulty_level: string
  visibility: string
  version: number
  created_at: string
}

export default function Watch() {
  const { id } = useParams<{ id: string }>()
  const [video, setVideo] = useState<VideoDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const { token } = useAuth()

  useEffect(() => {
    if (id) {
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`

      fetch(`${API_BASE}/api/videos/${id}`, { headers })
        .then((res) => res.json())
        .then((data) => {
          setVideo(data)
          setLoading(false)
        })
        .catch(() => setLoading(false))
    }
  }, [id, token])

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="animate-pulse">
          <div className="aspect-video bg-gray-800 rounded-xl mb-6" />
          <div className="h-6 bg-gray-800 rounded w-1/2 mb-3" />
          <div className="h-4 bg-gray-800 rounded w-1/3" />
        </div>
      </div>
    )
  }

  if (!video) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 text-center">
        <h2 className="text-xl text-gray-400">Video not found</h2>
        <Link to="/" className="btn-primary mt-4 inline-block">Back to Library</Link>
      </div>
    )
  }

  if (video.status === 'processing' || video.status === 'pending') {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 text-center">
        <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-yellow-900/30 flex items-center justify-center">
          <svg className="w-8 h-8 text-yellow-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-gray-200 mb-2">{video.title}</h2>
        <p className="text-gray-400">Video is being generated... This may take a few minutes.</p>
        <p className="text-sm text-gray-500 mt-2">Status: {video.status}</p>
      </div>
    )
  }

  const difficultyLabels: Record<string, string> = {
    basic: 'Core Foundation',
    platform_deep_dive: 'Platform Deep Dive',
    advanced: 'Advanced',
  }

  const absolutize = (u: string | null | undefined) => {
    if (!u) return u ?? null
    return /^https?:\/\//i.test(u) ? u : `${API_BASE}${u}`
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {video.video_url && (
        <VideoPlayer
          videoUrl={absolutize(video.video_url) as string}
          title={video.title}
          transcriptUrl={absolutize(video.transcript_url)}
          downloadUrl={`${API_BASE}/api/videos/${video.id}/download`}
        />
      )}

      <div className="mt-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs px-2 py-0.5 rounded-full bg-brand-purple-light/20 text-brand-purple-light font-medium">
            {difficultyLabels[video.difficulty_level] || video.difficulty_level}
          </span>
          {video.visibility === 'private' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
              Private
            </span>
          )}
        </div>
        <h1 className="text-2xl font-bold text-gray-100">{video.title}</h1>
        {video.description && (
          <p className="text-gray-400 mt-2">{video.description}</p>
        )}
        <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
          {video.duration_seconds && (
            <span>{Math.round(video.duration_seconds / 60)} min</span>
          )}
          <span>Version {video.version}</span>
          <span>{new Date(video.created_at).toLocaleDateString()}</span>
        </div>

        <div className="flex gap-3 mt-6">
          <a
            href={`${API_BASE}/api/videos/${video.id}/download`}
            download
            className="btn-secondary flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Video (MP4)
          </a>

          <a
            href={absolutize(video.transcript_url) || '#'}
            download
            className="btn-secondary flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Download Transcript (VTT)
          </a>
        </div>
      </div>
    </div>
  )
}
