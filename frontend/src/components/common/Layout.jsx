import { Link, useLocation } from 'react-router-dom'
import { Leaf, LayoutDashboard, Upload, ClipboardCheck, History, LogOut, User } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/ingest',    icon: Upload,          label: 'Ingest Data' },
  { to: '/review',    icon: ClipboardCheck,  label: 'Review Records' },
  { to: '/batches',   icon: History,         label: 'Batch History' },
]

export default function Layout({ children }) {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-60 bg-gray-900 flex flex-col shrink-0">
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-gray-800">
          <div className="w-8 h-8 bg-brand-500 rounded-lg flex items-center justify-center">
            <Leaf size={16} className="text-white" />
          </div>
          <div>
            <p className="text-white text-sm font-semibold leading-tight">Breathe ESG</p>
            <p className="text-gray-500 text-xs">Data Platform</p>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label }) => {
            const active = pathname.startsWith(to)
            return (
              <Link
                key={to} to={to}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  active
                    ? 'bg-brand-600/20 text-brand-400 font-medium'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                <Icon size={16} />
                {label}
              </Link>
            )
          })}
        </nav>

        <div className="px-3 py-4 border-t border-gray-800">
          <div className="flex items-center gap-2.5 px-3 py-2 mb-1">
            <div className="w-7 h-7 rounded-full bg-brand-700 flex items-center justify-center">
              <User size={13} className="text-brand-200" />
            </div>
            <div className="min-w-0">
              <p className="text-white text-xs font-medium truncate">{user?.username}</p>
              <p className="text-gray-500 text-xs capitalize">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full px-3 py-2 text-gray-400 hover:text-white text-sm rounded-lg hover:bg-gray-800 transition-colors"
          >
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 overflow-auto">
        {children}
      </main>
    </div>
  )
}
