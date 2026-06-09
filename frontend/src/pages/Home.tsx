import VideoLibrary from '../components/VideoLibrary'

export default function Home() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
          Video Nuggets Library
        </h1>
        <p className="text-gray-400 mt-2">
          Bite-sized, narrated video lessons generated from plain documents — with charts, captions, and a Q&amp;A bot.
        </p>
      </div>
      <VideoLibrary />
    </div>
  )
}
