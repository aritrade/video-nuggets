import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { API_BASE } from '../lib/api'

interface Video {
  id: number
  title: string
  description: string
  status: string
  duration_seconds: number | null
  thumbnail_url: string | null
  playlist_id: number | null
  difficulty_level: string
  visibility: string
  playlist_order: number
  created_at: string
}

interface DifficultySection {
  key: string
  name: string
  videos: Video[]
}

interface PlaylistGroup {
  id: number | null
  name: string
  description: string | null
  is_default: boolean
  sections: DifficultySection[]
  total_videos: number
}

const DIFFICULTY_ICONS: Record<string, string> = {
  basic: 'CF',
  platform_deep_dive: 'PDD',
  advanced: 'ADV',
}

const DIFFICULTY_GRADIENTS: Record<string, string> = {
  basic: 'from-green-400 to-emerald-600',
  platform_deep_dive: 'from-brand-purple-light to-brand-teal',
  advanced: 'from-orange-400 to-red-500',
}

export default function VideoLibrary() {
  const [playlists, setPlaylists] = useState<PlaylistGroup[]>([])
  const [loading, setLoading] = useState(true)
  const { token } = useAuth()

  useEffect(() => {
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    fetch(`${API_BASE}/api/videos/`, { headers })
      .then((res) => res.json())
      .then((data) => {
        setPlaylists(data.playlists || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="space-y-12">
        {[1, 2].map((i) => (
          <div key={i}>
            <div className="h-8 bg-gray-800 rounded w-64 mb-6 animate-pulse" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {[...Array(4)].map((_, j) => (
                <div key={j} className="card animate-pulse">
                  <div className="aspect-video bg-gray-800 rounded-lg mb-3" />
                  <div className="h-4 bg-gray-800 rounded w-3/4 mb-2" />
                  <div className="h-3 bg-gray-800 rounded w-1/2" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  const hasVideos = playlists.some((p) => p.total_videos > 0)

  if (!hasVideos) {
    return (
      <div className="text-center py-20">
        <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-brand-purple-light/20 to-brand-teal/20 flex items-center justify-center">
          <svg className="w-10 h-10 text-brand-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        </div>
        <h3 className="text-xl font-semibold text-gray-300 mb-2">No videos yet</h3>
        <p className="text-gray-500 mb-6">Upload content to generate your first video nugget</p>
        <Link to="/upload" className="btn-primary">Upload Content</Link>
      </div>
    )
  }

  return (
    <div className="space-y-16">
      {playlists
        .filter((p) => p.total_videos > 0)
        .map((playlist) => (
          <section key={playlist.id ?? 'orphan'}>
            <div className="border-b border-gray-800 pb-4 mb-8">
              <div className="flex items-baseline gap-3 flex-wrap">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
                  {playlist.name}
                </h2>
                {playlist.is_default && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand-purple-light/20 text-brand-purple-light font-semibold uppercase tracking-wider">
                    Default
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  {playlist.total_videos} video{playlist.total_videos !== 1 ? 's' : ''}
                </span>
              </div>
              {playlist.description && (
                <p className="text-sm text-gray-400 mt-2">{playlist.description}</p>
              )}
            </div>

            <div className="space-y-10">
              {playlist.sections.map((section) => (
                <div key={section.key}>
                  <div className="flex items-center gap-3 mb-4">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold tracking-wider bg-gradient-to-r ${DIFFICULTY_GRADIENTS[section.key]} text-white`}>
                      {DIFFICULTY_ICONS[section.key]}
                    </span>
                    <h3 className="text-lg font-semibold text-gray-200">{section.name}</h3>
                    <span className="text-xs text-gray-500">{section.videos.length}</span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {section.videos.map((video, index) => (
                      <Link key={video.id} to={`/watch/${video.id}`} className="card group cursor-pointer relative">
                        {video.visibility === 'private' && (
                          <span className="absolute top-3 left-3 z-10 text-[10px] px-2 py-0.5 rounded-full bg-red-500/80 text-white font-medium uppercase tracking-wider">
                            Private
                          </span>
                        )}
                        <div className="aspect-video bg-gray-800 rounded-lg mb-3 overflow-hidden relative">
                          {video.thumbnail_url ? (
                            <img src={`${API_BASE}${video.thumbnail_url}`} alt={video.title} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-brand-purple/30 to-brand-deep-purple/30">
                              <span className="text-3xl font-bold text-brand-purple-light/30">{index + 1}</span>
                            </div>
                          )}
                          {video.duration_seconds && (
                            <span className="absolute bottom-2 right-2 bg-black/80 text-[10px] text-white px-1.5 py-0.5 rounded font-mono">
                              {Math.floor(video.duration_seconds / 60)}:{Math.floor(video.duration_seconds % 60).toString().padStart(2, '0')}
                            </span>
                          )}
                          {video.status !== 'ready' && (
                            <span className="absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded-full bg-yellow-500/80 text-white font-medium uppercase">
                              {video.status}
                            </span>
                          )}
                          <div className="absolute inset-0 bg-brand-purple-light/0 group-hover:bg-brand-purple-light/10 transition-colors flex items-center justify-center">
                            <svg className="w-10 h-10 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-lg" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M8 5v14l11-7z" />
                            </svg>
                          </div>
                        </div>
                        <h4 className="font-medium text-sm text-gray-200 group-hover:text-brand-teal transition-colors line-clamp-2 leading-snug">
                          {video.title}
                        </h4>
                        <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{video.description}</p>
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
    </div>
  )
}
