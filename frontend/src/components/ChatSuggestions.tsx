interface ChatSuggestionsProps {
  suggestions: string[]
  onSelect: (text: string) => void
}

export default function ChatSuggestions({ suggestions, onSelect }: ChatSuggestionsProps) {
  return (
    <div className="px-4 pb-2">
      <p className="text-xs text-gray-500 mb-2">Try asking:</p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((suggestion, i) => (
          <button
            key={i}
            onClick={() => onSelect(suggestion)}
            className="text-sm bg-gray-900 border border-gray-700 hover:border-brand-purple-light text-gray-300 hover:text-white px-3 py-2 rounded-lg transition-colors"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  )
}
