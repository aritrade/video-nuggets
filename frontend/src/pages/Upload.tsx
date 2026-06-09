import UploadForm from '../components/UploadForm'

export default function Upload() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
          Generate Video Nugget
        </h1>
        <p className="text-gray-400 mt-2">
          Upload any document or paste a URL to create an auto-narrated video lecture
        </p>
      </div>
      <UploadForm />
    </div>
  )
}
