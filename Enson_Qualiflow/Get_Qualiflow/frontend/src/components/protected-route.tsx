import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../features/auth/auth-context'

export function ProtectedRoute() {
  const { isAuthenticated, isLoading, token } = useAuth()

  if (isLoading && token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <p className="text-sm text-slate-300">Loading session...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
