import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'
import { AppShell } from './components/app-shell'
import { ProtectedRoute } from './components/protected-route'
import { useAuth } from './features/auth/auth-context'
import { AnalysisDetailPage } from './pages/analysis-detail-page'
import { DashboardPage } from './pages/dashboard-page'
import { HistoryPage } from './pages/history-page'
import { LoginPage } from './pages/login-page'
import { RegisterPage } from './pages/register-page'

function GuestRoute({ children }: { children: ReactElement }) {
  const { isAuthenticated } = useAuth()
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }
  return children
}

function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <GuestRoute>
            <LoginPage />
          </GuestRoute>
        }
      />
      <Route
        path="/register"
        element={
          <GuestRoute>
            <RegisterPage />
          </GuestRoute>
        }
      />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/analysis/:id" element={<AnalysisDetailPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
