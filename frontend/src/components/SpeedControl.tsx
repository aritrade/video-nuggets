import { useState } from 'react'

interface SpeedControlProps {
  rate: number
  onChange: (rate: number) => void
}

const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2.0]

export default function SpeedControl({ rate, onChange }: SpeedControlProps) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="text-sm text-gray-400 hover:text-white px-2 py-1 rounded transition-colors"
      >
        {rate}x
      </button>

      {showMenu && (
        <div className="absolute bottom-full right-0 mb-2 bg-gray-900 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[80px]">
          {SPEEDS.map((speed) => (
            <button
              key={speed}
              onClick={() => {
                onChange(speed)
                setShowMenu(false)
              }}
              className={`w-full text-left px-3 py-1.5 text-sm transition-colors ${
                rate === speed
                  ? 'text-brand-teal bg-brand-teal/10'
                  : 'text-gray-300 hover:bg-gray-800'
              }`}
            >
              {speed}x
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
