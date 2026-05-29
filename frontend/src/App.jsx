import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Layout from './components/common/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Ingest from './pages/Ingest'
import Review from './pages/Review'
import Batches from './pages/Batches'

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-green-600 border-t-transparent" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/ingest"    element={<PrivateRoute><Ingest /></PrivateRoute>} />
          <Route path="/review"    element={<PrivateRoute><Review /></PrivateRoute>} />
          <Route path="/batches"   element={<PrivateRoute><Batches /></PrivateRoute>} />
          <Route path="*"          element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
