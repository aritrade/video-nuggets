import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import ChatBot from './ChatBot'

export default function NivaFab() {
  const [open, setOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (location.pathname === '/chat' || location.pathname === '/login') {
    return null
  }

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        aria-label={open ? 'Close NuggetBot chat' : 'Open NuggetBot chat'}
        className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-brand-purple-light to-brand-teal shadow-lg hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center group"
      >
        {open ? (
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <>
            <span className="text-white font-bold text-xl">N</span>
            <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-brand-teal rounded-full border-2 border-gray-900 animate-pulse" />
          </>
        )}
        {!open && (
          <span className="absolute right-full mr-3 px-3 py-1.5 bg-gray-900 text-white text-xs font-medium rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none border border-gray-700">
            Ask NuggetBot
          </span>
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30 md:bg-transparent md:backdrop-blur-none"
          onClick={() => setOpen(false)}
        />
      )}

      <div
        className={`fixed bottom-24 right-6 z-40 w-[calc(100vw-3rem)] sm:w-96 md:w-[420px] h-[600px] max-h-[calc(100vh-7rem)] bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden transition-all duration-300 origin-bottom-right ${
          open ? 'opacity-100 scale-100' : 'opacity-0 scale-95 pointer-events-none'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gradient-to-r from-brand-purple-light/10 to-brand-teal/10 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-purple-light to-brand-teal flex items-center justify-center">
              <span className="text-white font-bold text-xs">N</span>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white leading-tight">NuggetBot</h3>
              <p className="text-[10px] text-gray-400 leading-tight">Your video-library Q&amp;A assistant</p>
            </div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-gray-400 hover:text-white p-1"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-hidden">
          <ChatBot compact />
        </div>
      </div>
    </>
  )
}
