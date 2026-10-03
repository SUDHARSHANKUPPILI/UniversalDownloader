import { useState, useEffect } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Download,
  ListOrdered,
  History,
  Folder,
  Settings,
  Shield,
  BarChart3,
  Menu,
  X,
  Sun,
  Moon,
  Monitor,
  HardDrive,
  ChevronLeft,
} from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import NotificationContainer from './NotificationContainer'
import { api } from '../../services/api'
import type { Statistics } from '../../types'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/downloads', label: 'Downloads', icon: Download },
  { path: '/queue', label: 'Queue', icon: ListOrdered },
  { path: '/history', label: 'History', icon: History },
  { path: '/files', label: 'Files', icon: Folder },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: Settings },
  { path: '/security', label: 'Security', icon: Shield },
]

function formatBytes(bytes?: number | null): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unitIndex = 0
  let value = bytes
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function getPageLabel(pathname: string): string {
  const item = NAV_ITEMS.find((n) => n.path === pathname)
  return item?.label ?? 'Dashboard'
}

export default function RootLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { theme, setTheme, resolved } = useTheme()
  const location = useLocation()
  const [stats, setStats] = useState<Statistics | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getStatistics().then((res) => {
      if (!cancelled) setStats(res)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  return (
    <div className="flex h-screen bg-[var(--bg)] text-[var(--fg)] overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 flex flex-col
          transition-all duration-300 ease-in-out
          ${sidebarCollapsed ? 'w-[72px]' : 'w-64'}
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
        style={{
          background: 'var(--sidebar)',
          backdropFilter: 'blur(24px) saturate(1.4)',
          WebkitBackdropFilter: 'blur(24px) saturate(1.4)',
          borderRight: '1px solid var(--card-border)',
        }}
      >
        {/* Logo area */}
        <div
          className="flex items-center justify-between px-4 h-[60px] flex-shrink-0"
          style={{ borderBottom: '1px solid var(--card-border)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            {/* Logo icon */}
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{
                background: 'linear-gradient(135deg, var(--accent) 0%, #3b5fc8 100%)',
                boxShadow: '0 2px 12px var(--accent-glow)',
              }}
            >
              <Download className="w-4 h-4 text-white" />
            </div>
            {!sidebarCollapsed && (
              <div className="min-w-0">
                <p className="text-[13px] font-bold tracking-tight leading-none text-[var(--fg)] truncate">
                  UniversalDL
                </p>
                <p className="text-[10px] text-[var(--muted)] mt-0.5 leading-none font-medium">
                  Download Manager
                </p>
              </div>
            )}
          </div>
          <button
            className="lg:hidden p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)] transition-colors"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Nav section */}
        <nav className="flex-1 overflow-y-auto scrollbar-none py-3 px-2">
          {!sidebarCollapsed && (
            <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted)]">
              Navigation
            </p>
          )}
          <div className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setSidebarOpen(false)}
                  title={sidebarCollapsed ? item.label : undefined}
                  className={`
                    relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium
                    transition-all duration-150
                    ${isActive
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)]'
                    }
                  `}
                  style={isActive ? {
                    background: 'linear-gradient(90deg, var(--accent-subtle), transparent 80%)',
                    boxShadow: 'inset 3px 0 0 var(--accent)',
                  } : {}}
                >
                  <Icon className="w-[18px] h-[18px] flex-shrink-0" />
                  {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
                </Link>
              )
            })}
          </div>
        </nav>

        {/* Storage indicator */}
        {stats && !sidebarCollapsed && (
          <div className="mx-3 mb-3 px-3 py-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--card-border)' }}>
            <div className="flex items-center gap-2 mb-1.5">
              <HardDrive className="w-3.5 h-3.5 text-[var(--muted)]" />
              <span className="text-[11px] text-[var(--muted)] font-medium">Storage</span>
            </div>
            <p className="text-sm font-semibold">{formatBytes(stats.storage_used)}</p>
            <p className="text-[11px] text-[var(--muted)] mt-0.5">
              {stats.completed} completed · {stats.active} active
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="flex-shrink-0 px-2 pb-3 pt-2 space-y-0.5" style={{ borderTop: '1px solid var(--card-border)' }}>
          {/* Theme row */}
          <div className={`flex items-center ${sidebarCollapsed ? 'flex-col gap-0.5' : 'gap-1 px-1'}`}>
            {[
              { value: 'light' as const, icon: Sun, label: 'Light' },
              { value: 'dark' as const, icon: Moon, label: 'Dark' },
              { value: 'system' as const, icon: Monitor, label: 'System' },
            ].map(({ value, icon: Icon, label }) => {
              const isActive = value === 'system' ? theme === 'system' : resolved === value
              return (
                <button
                  key={value}
                  onClick={() => setTheme(value)}
                  title={label}
                  className={`flex-1 flex items-center justify-center p-2 rounded-lg transition-all ${
                    isActive
                      ? 'bg-[var(--accent-subtle)] text-[var(--accent)]'
                      : 'text-[var(--muted)] hover:bg-[var(--card-hover)] hover:text-[var(--fg)]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                </button>
              )
            })}
          </div>

          {/* Collapse toggle */}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="hidden lg:flex w-full items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] text-[var(--muted)] hover:bg-[var(--card-hover)] hover:text-[var(--fg)] transition-all"
          >
            <ChevronLeft
              className={`w-[18px] h-[18px] flex-shrink-0 transition-transform duration-300 ${sidebarCollapsed ? 'rotate-180' : ''}`}
            />
            {!sidebarCollapsed && <span className="font-medium">Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div
        className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${
          sidebarCollapsed ? 'lg:ml-[72px]' : 'lg:ml-64'
        }`}
      >
        {/* Top bar */}
        <header
          className="flex-shrink-0 h-[60px] flex items-center gap-4 px-6"
          style={{
            background: 'var(--header)',
            backdropFilter: 'blur(16px) saturate(1.2)',
            WebkitBackdropFilter: 'blur(16px) saturate(1.2)',
            borderBottom: '1px solid var(--card-border)',
          }}
        >
          {/* Mobile hamburger */}
          <button
            aria-label="Open navigation menu"
            className="lg:hidden p-2 rounded-xl text-[var(--muted)] hover:bg-[var(--card-hover)] hover:text-[var(--fg)] transition-colors"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Page label */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-[var(--muted)] text-xs">UniversalDL</span>
            <span className="text-[var(--muted)] text-xs">/</span>
            <span className="font-semibold text-[var(--fg)] text-sm">
              {getPageLabel(location.pathname)}
            </span>
          </div>

          {/* Status pills */}
          {stats && (stats.active + stats.queued) > 0 && (
            <div className="flex items-center gap-2 ml-4">
              <span
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold"
                style={{ background: 'var(--info-subtle)', color: 'var(--info)' }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                {stats.active + stats.queued} active
              </span>
            </div>
          )}

          <div className="ml-auto" />

          {/* Render notifications portal anchor — it renders to body */}
          <NotificationContainer />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-[1400px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}