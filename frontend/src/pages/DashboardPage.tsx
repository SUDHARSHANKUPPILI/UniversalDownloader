import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download as DownloadIcon, CheckCircle2, AlertCircle, ListOrdered, FileText, HardDrive, Plus } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../services/api'
import { StatCard } from '../components/ui'
import { formatNumber, formatBytes } from '../components/utils/formatters'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import StatusBadge from '../components/ui/StatusBadge'
import type { Download, Statistics } from '../types'

export default function DashboardPage() {
  const [stats, setStats] = useState<Statistics | null>(null)
  const [recentDownloads, setRecentDownloads] = useState<Download[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const [statsRes, dlRes] = await Promise.all([
        api.getStatistics(),
        api.getDownloads({ per_page: '6', order: 'created_at', direction: 'desc' }),
      ])
      setStats(statsRes)
      setRecentDownloads(dlRes.downloads)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  // Smart polling while active downloads exist
  useEffect(() => {
    const hasActive = (stats?.active ?? 0) > 0 || (stats?.queued ?? 0) > 0
    if (!hasActive) return
    const interval = setInterval(loadData, 2000)
    return () => clearInterval(interval)
  }, [stats?.active, stats?.queued])

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Overview of your downloads and system status"
        action={
          <Link to="/downloads" className="btn btn-primary btn-sm gap-2">
            <Plus className="w-3.5 h-3.5" />
            Add Download
          </Link>
        }
      />

      {loading ? (
        <LoadingSpinner label="Loading dashboard…" />
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 mb-7">
        {[
          { label: 'Total', value: formatNumber(stats?.total ?? 0), icon: FileText, accent: undefined },
          { label: 'Active', value: formatNumber((stats?.active ?? 0) + (stats?.queued ?? 0)), icon: DownloadIcon, accent: '#60a5fa' },
          { label: 'Completed', value: formatNumber(stats?.completed ?? 0), icon: CheckCircle2, accent: '#34d399' },
          { label: 'Failed', value: formatNumber(stats?.failed ?? 0), icon: AlertCircle, accent: '#f87171' },
          { label: 'Queued', value: formatNumber(stats?.queued ?? 0), icon: ListOrdered, accent: '#fbbf24' },
          { label: 'Storage', value: formatBytes(stats?.storage_used ?? 0), icon: HardDrive, accent: '#a78bfa' },
        ].map((card) => (
          <StatCard key={card.label} {...card} />
        ))}
      </div>

      {/* Recent downloads */}
      <div className="card overflow-hidden">
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: '1px solid var(--card-border)' }}
        >
          <h2 className="font-semibold text-[15px]">Recent Downloads</h2>
          <Link to="/downloads" className="text-xs text-[var(--accent)] hover:underline font-medium">
            View all →
          </Link>
        </div>

        {recentDownloads.length === 0 ? (
          <div className="py-6">
            <EmptyState
              title="No downloads yet"
              description="Add your first download to get started"
            />
          </div>
        ) : (
          <div>
            {recentDownloads.map((dl, i) => (
              <motion.div
                key={dl.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-4 px-5 py-3.5 hover:bg-[var(--bg-subtle)] transition-colors"
                style={{ borderBottom: i < recentDownloads.length - 1 ? '1px solid var(--card-border)' : undefined }}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-[13px] truncate">{dl.title}</p>
                  <p className="text-[11px] text-[var(--muted)] mt-0.5 capitalize">
                    {dl.media_type || 'video'} · {dl.quality || 'best'}
                    {dl.total_size ? ` · ${formatBytes(dl.total_size)}` : ''}
                  </p>
                </div>
                <StatusBadge status={dl.status} />
              </motion.div>
            ))}
          </div>
        )}
      </div>
        </>
      )}
    </div>
  )
}
