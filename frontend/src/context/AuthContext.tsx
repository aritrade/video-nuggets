import { createContext, useCallback, useContext, useState, useEffect, ReactNode } from 'react'
import { API_BASE } from '../lib/api'

interface UserInfo {
  id: number
  username: string
  display_name: string
  role: string
  email: string
}

interface AuthContextType {
  user: UserInfo | null
  token: string | null
  isAdmin: boolean
  isNutanix: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  /**
   * Wrapper around `fetch` that injects the bearer token and, when the server
   * answers 401, clears the persisted session so the UI can prompt for a fresh
   * sign-in instead of showing a raw "HTTP 401" error.
   */
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  loading: boolean
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAdmin: false,
  isNutanix: false,
  login: async () => {},
  logout: () => {},
  authFetch: async () => new Response(null, { status: 0 }),
  loading: true,
})

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
  }, [])

  // Restore + validate persisted session. The JWT has a 24h lifetime on the
  // backend, so a stale localStorage entry must not be trusted blindly --
  // otherwise admin pages render and then fail every request with HTTP 401.
  useEffect(() => {
    let cancelled = false
    const savedToken = localStorage.getItem('auth_token')
    const savedUser = localStorage.getItem('auth_user')

    if (!savedToken || !savedUser) {
      setLoading(false)
      return
    }

    setToken(savedToken)
    try {
      setUser(JSON.parse(savedUser))
    } catch {
      logout()
      setLoading(false)
      return
    }

    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${savedToken}` },
    })
      .then(async (res) => {
        if (cancelled) return
        if (res.status === 401) {
          logout()
          return
        }
        if (res.ok) {
          const fresh = await res.json()
          setUser(fresh)
          localStorage.setItem('auth_user', JSON.stringify(fresh))
        }
      })
      .catch(() => {
        // Network failure: keep the cached session so the user isn't kicked
        // out just because the backend is briefly unreachable.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [logout])

  const login = async (username: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    setToken(data.access_token)
    setUser(data.user)
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('auth_user', JSON.stringify(data.user))
  }

  const authFetch = useCallback<AuthContextType['authFetch']>(
    async (input, init = {}) => {
      const headers = new Headers(init.headers)
      if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`)
      }
      const res = await fetch(input, { ...init, headers })
      if (res.status === 401) {
        logout()
      }
      return res
    },
    [token, logout]
  )

  const isAdmin = user?.role === 'admin'
  const isNutanix = user?.role === 'admin' || user?.role === 'viewer'

  return (
    <AuthContext.Provider value={{ user, token, isAdmin, isNutanix, login, logout, authFetch, loading }}>
      {children}
    </AuthContext.Provider>
  )
}
