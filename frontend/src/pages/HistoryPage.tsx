import { useEffect, useState } from 'react'
import { CheckCircle2, AlertCircle, XCircle, History } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import StatusBadge from '../components/ui/StatusBadge'
import { formatRelativeTime, formatBytes } from '../components/utils/formatters'
import type { Download } from '../types'

export default function HistoryPage() {
  const [history, setHistory] = useState<Download[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const res = await api.getHistory(50, 0)
      setHistory(res.history)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle2 className="w-4 h-4 text-[var(--success)]" />
      case 'failed': return <AlertCircle className="w-4 h-4 text-[var(--danger)]" />
      case 'cancelled': return <XCircle className="w-4 h-4 text-[var(--muted)]" />
      default: return null
    }
  }

  return (
    <div>
      <PageHeader
        title="History"
        description="Browse completed and past downloads"
        action={
          history.length > 0 ? (
            <span className="text-sm text-[var(--muted)] font-medium">{history.length} entries</span>
          ) : undefined
        }
      />

      {loading ? (
        <LoadingSpinner label="Loading history…" />
      ) : history.length === 0 ? (
        <EmptyState
          icon={History}
          title="No history yet"
          description="Completed and failed downloads will appear here"
        />
      ) : (
        <div className="card overflow-x-auto">
          <div className="min-w-[620px]">
            {/* Header */}
            <div
              className="grid items-center gap-4 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-widest text-[var(--muted)]"
            style={{
              gridTemplateColumns: '32px 1fr 90px 120px 72px 100px',
              borderBottom: '1px solid var(--card-border)',
            }}
          >
            <span />
            <span>Title</span>
            <span>Quality</span>
            <span>Status</span>
            <span>Size</span>
            <span>Added</span>
          </div>

          {history.map((dl, i) => (
            <motion.div
              key={dl.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.025, duration: 0.18 }}
              className="grid items-center gap-4 px-5 py-3.5 hover:bg-[var(--bg-subtle)] transition-colors"
              style={{
                gridTemplateColumns: '32px 1fr 90px 120px 72px 100px',
                borderBottom: i < history.length - 1 ? '1px solid var(--card-border)' : undefined,
              }}
            >
              {/* Status icon */}
              <div className="flex justify-center">{getStatusIcon(dl.status)}</div>

              {/* Title */}
              <p className="font-medium text-[13px] truncate" title={dl.title}>{dl.title}</p>

              {/* Quality */}
              <span className="text-xs text-[var(--muted)] font-mono">{dl.quality || 'best'}</span>

              {/* Badge */}
              <StatusBadge status={dl.status} />

              {/* Size */}
              <span className="text-xs text-[var(--muted)] font-mono">{formatBytes(dl.total_size)}</span>

              {/* Time */}
              <span className="text-xs text-[var(--muted)]">{formatRelativeTime(dl.created_at)}</span>
            </motion.div>
          ))}
          </div>
        </div>
      )}
    </div>
  )
}