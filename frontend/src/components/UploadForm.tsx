import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { API_BASE } from '../lib/api'
const ACCEPTED_TYPES = '.pdf,.pptx,.txt,.png,.jpg,.jpeg'
const NEW_PLAYLIST_VALUE = '__new__'

interface PlaylistOption {
  id: number
  name: string
  is_default: boolean
}

export default function UploadForm() {
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [difficultyLevel, setDifficultyLevel] = useState('basic')
  const [visibility, setVisibility] = useState('public')
  const [playlists, setPlaylists] = useState<PlaylistOption[]>([])
  const [selectedPlaylist, setSelectedPlaylist] = useState<string>('')
  const [showCreatePlaylist, setShowCreatePlaylist] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')
  const [newPlaylistDesc, setNewPlaylistDesc] = useState('')
  const [creatingPlaylist, setCreatingPlaylist] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [mode, setMode] = useState<'file' | 'url'>('file')
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { token, isAdmin } = useAuth()

  useEffect(() => {
    if (!isAdmin) return
    fetch(`${API_BASE}/api/playlists/`)
      .then((res) => res.json())
      .then((data) => {
        const list: PlaylistOption[] = (data.playlists || []).map((p: any) => ({
          id: p.id,
          name: p.name,
          is_default: p.is_default,
        }))
        setPlaylists(list)
        const def = list.find((p) => p.is_default) || list[0]
        if (def) setSelectedPlaylist(String(def.id))
      })
      .catch(() => {})
  }, [isAdmin])

  if (!isAdmin) {
    return (
      <div className="text-center py-20">
        <h3 className="text-xl font-semibold text-gray-300 mb-2">Access Denied</h3>
        <p className="text-gray-500">Only admins can upload content. Sign in with the demo admin account to try it.</p>
      </div>
    )
  }

  const handlePlaylistChange = (val: string) => {
    if (val === NEW_PLAYLIST_VALUE) {
      setShowCreatePlaylist(true)
    } else {
      setSelectedPlaylist(val)
      setShowCreatePlaylist(false)
    }
  }

  const handleCreatePlaylist = async () => {
    if (!newPlaylistName.trim()) {
      setError('Playlist name is required')
      return
    }
    setCreatingPlaylist(true)
    setError('')
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(`${API_BASE}/api/playlists/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ name: newPlaylistName.trim(), description: newPlaylistDesc.trim() || null }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to create playlist')
      }
      const created = await res.json()
      const newOption: PlaylistOption = { id: created.id, name: created.name, is_default: false }
      setPlaylists((prev) => [...prev, newOption])
      setSelectedPlaylist(String(created.id))
      setShowCreatePlaylist(false)
      setNewPlaylistName('')
      setNewPlaylistDesc('')
    } catch (err: any) {
      setError(err.message || 'Failed to create playlist')
    } finally {
      setCreatingPlaylist(false)
    }
  }

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setUploading(true)
    setError('')

    try {
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`

      let response: Response

      const buildBody = () => {
        const formData = new FormData()
        if (title) formData.append('title', title)
        formData.append('difficulty_level', difficultyLevel)
        formData.append('visibility', visibility)
        if (selectedPlaylist) formData.append('playlist_id', selectedPlaylist)
        return formData
      }

      if (mode === 'file' && file) {
        const formData = buildBody()
        formData.append('file', file)
        response = await fetch(`${API_BASE}/api/uploads/file`, { method: 'POST', body: formData, headers })
      } else if (mode === 'url' && url) {
        const formData = buildBody()
        formData.append('url', url)
        response = await fetch(`${API_BASE}/api/uploads/url`, { method: 'POST', body: formData, headers })
      } else {
        return
      }

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Upload failed')
      }

      const data = await response.json()
      if (data.id) {
        navigate(`/watch/${data.id}`)
      }
    } catch (err: any) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto space-y-6">
      <div className="flex gap-2 bg-gray-900 p-1 rounded-lg w-fit">
        <button
          type="button"
          onClick={() => setMode('file')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'file' ? 'bg-brand-purple-light text-white' : 'text-gray-400 hover:text-white'
          }`}
        >
          Upload File
        </button>
        <button
          type="button"
          onClick={() => setMode('url')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'url' ? 'bg-brand-purple-light text-white' : 'text-gray-400 hover:text-white'
          }`}
        >
          From URL
        </button>
      </div>

      {mode === 'file' ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleFileDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
            dragOver ? 'border-brand-teal bg-brand-teal/5' : 'border-gray-700 hover:border-brand-purple-light'
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="hidden"
          />
          <svg className="w-12 h-12 mx-auto text-gray-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          {file ? (
            <p className="text-brand-teal font-medium">{file.name}</p>
          ) : (
            <>
              <p className="text-gray-300 font-medium">Drop your file here or click to browse</p>
              <p className="text-gray-500 text-sm mt-2">Supports PDF, PPTX, TXT, PNG, JPG</p>
            </>
          )}
        </div>
      ) : (
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
          />
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-400 mb-2">Title (optional)</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Video title"
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-400 mb-2">Playlist</label>
        <select
          value={showCreatePlaylist ? NEW_PLAYLIST_VALUE : selectedPlaylist}
          onChange={(e) => handlePlaylistChange(e.target.value)}
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
        >
          {playlists.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.is_default ? ' (Default)' : ''}
            </option>
          ))}
          <option value={NEW_PLAYLIST_VALUE}>+ Create new playlist...</option>
        </select>

        {showCreatePlaylist && (
          <div className="mt-3 p-4 bg-gray-900 border border-brand-purple-light/40 rounded-lg space-y-3">
            <input
              type="text"
              value={newPlaylistName}
              onChange={(e) => setNewPlaylistName(e.target.value)}
              placeholder="New playlist name"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:border-brand-purple-light outline-none text-sm"
            />
            <input
              type="text"
              value={newPlaylistDesc}
              onChange={(e) => setNewPlaylistDesc(e.target.value)}
              placeholder="Description (optional)"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:border-brand-purple-light outline-none text-sm"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreatePlaylist}
                disabled={creatingPlaylist || !newPlaylistName.trim()}
                className="flex-1 px-4 py-2 bg-gradient-to-r from-brand-purple-light to-brand-teal text-white text-sm font-medium rounded-lg disabled:opacity-50"
              >
                {creatingPlaylist ? 'Creating...' : 'Create Playlist'}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreatePlaylist(false); setNewPlaylistName(''); setNewPlaylistDesc('') }}
                className="px-4 py-2 border border-gray-600 text-gray-300 text-sm font-medium rounded-lg hover:border-gray-400"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Difficulty</label>
          <select
            value={difficultyLevel}
            onChange={(e) => setDifficultyLevel(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
          >
            <option value="basic">Core Foundation (Basic)</option>
            <option value="platform_deep_dive">Platform Deep Dive</option>
            <option value="advanced">Advanced</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Visibility</label>
          <select
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white focus:border-brand-purple-light focus:ring-1 focus:ring-brand-purple-light outline-none"
          >
            <option value="public">Public (accessible by all)</option>
            <option value="private">Private (signed-in users only)</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={uploading || (mode === 'file' && !file) || (mode === 'url' && !url)}
        className="w-full btn-primary py-3 text-lg disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {uploading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Generating Video...
          </span>
        ) : (
          'Generate Video Nugget'
        )}
      </button>
    </form>
  )
}
