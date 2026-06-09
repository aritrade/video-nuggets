import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Watch from './pages/Watch'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Login from './pages/Login'
import Monitor from './pages/Monitor'
import Architecture from './pages/Architecture'
import Navbar from './components/Navbar'
import NivaFab from './components/NivaFab'
import { AuthProvider } from './context/AuthContext'

export default function App() {
  return (
    <AuthProvider>
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/watch/:id" element={<Watch />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/login" element={<Login />} />
            <Route path="/monitor" element={<Monitor />} />
            <Route path="/architecture" element={<Architecture />} />
          </Routes>
        </main>
        <NivaFab />
      </div>
    </AuthProvider>
  )
}
