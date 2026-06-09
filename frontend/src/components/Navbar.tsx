import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const location = useLocation()
  const { user, isAdmin, logout } = useAuth()

  const links = [
    { to: '/', label: 'Library', show: true },
    { to: '/architecture', label: 'Architecture', show: true },
    { to: '/upload', label: 'Upload', show: isAdmin },
    { to: '/chat', label: 'Ask NuggetBot', show: true },
    { to: '/monitor', label: 'Monitor', show: isAdmin },
  ]

  const roleLabel: Record<string, string> = {
    guest: 'Guest',
    viewer: 'Viewer',
    admin: 'Admin',
  }

  return (
    <nav className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-purple-light to-brand-teal flex items-center justify-center">
              <span className="text-white font-bold text-sm">V</span>
            </div>
            <span className="text-lg font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
              Video Nuggets OS
            </span>
          </Link>

          <div className="flex items-center gap-1">
            {links
              .filter((l) => l.show)
              .map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
                    location.pathname === link.to
                      ? 'bg-brand-purple-light/20 text-brand-teal'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
          </div>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                <span className="text-xs px-2.5 py-1 rounded-full bg-brand-purple-light/20 text-brand-purple-light font-medium">
                  {roleLabel[user.role] || user.role}
                </span>
                <span className="text-sm text-gray-300">{user.display_name}</span>
                <button
                  onClick={logout}
                  className="text-xs px-3 py-1.5 rounded-lg border border-gray-600 text-gray-400 hover:text-white hover:border-gray-400 transition-colors"
                >
                  Logout
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="text-sm px-4 py-2 rounded-lg bg-gradient-to-r from-brand-purple-light to-brand-teal text-white font-medium hover:opacity-90 transition-opacity"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}
