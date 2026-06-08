import { History, LogOut, UploadCloud } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Button } from './ui/button'
import { useAuth } from '../features/auth/auth-context'

function NavLink({ to, label, icon }: { to: string; label: string; icon: ReactNode }) {
  const location = useLocation()
  const active = location.pathname === to
  return (
    <Link
      to={to}
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
        active ? 'bg-sky-500 text-slate-950' : 'border border-slate-700 text-slate-200 hover:bg-slate-800'
      }`}
    >
      {icon}
      {label}
    </Link>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-sky-400">QualiFlow</p>
            <p className="text-sm text-slate-300">{user?.email}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <NavLink to="/" label="Analyze" icon={<UploadCloud className="h-4 w-4" />} />
            <NavLink to="/history" label="History" icon={<History className="h-4 w-4" />} />
            <Button
              variant="ghost"
              onClick={() => {
                logout()
                navigate('/login')
              }}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
        <Outlet />
      </div>
    </div>
  )
}
