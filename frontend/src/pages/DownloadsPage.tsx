import { useEffect, useState } from 'react'
import { Plus, Download as DownloadIcon, CheckCircle2, AlertCircle, Clock, XCircle } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import { api } from '../services/api'
import DownloadCard from '../components/Downloads/DownloadCard'
import AddDownloadForm from '../components/Forms/AddDownloadForm'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import type { Download } from '../types'

type FilterKey = 'all' | 'active' | 'completed' | 'failed'

const FILTERS: { key: FilterKey; label: string; icon: React.ReactNode }[] = [
  { key: 'all', label: 'All', icon: <DownloadIcon className="w-3.5 h-3.5" /> },
  { key: 'active', label: 'Active', icon: <Clock className="w-3.5 h-3.5" /> },
  { key: 'completed', label: 'Completed', icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
  { key: 'failed', label: 'Failed', icon: <AlertCircle className="w-3.5 h-3.5" /> },
]

function filterDownloads(downloads: Download[], filter: FilterKey): Download[] {
  switch (filter) {
    case 'active': return downloads.filter((d) => d.status === 'downloading' || d.status === 'queued' || d.status === 'paused')
    case 'completed': return downloads.filter((d) => d.status === 'completed')
    case 'failed': return downloads.filter((d) => d.status === 'failed' || d.status === 'cancelled')
    default: return downloads
  }
}

function filterCount(downloads: Download[], filter: FilterKey): number {
  return filterDownloads(downloads, filter).length
}

export default function DownloadsPage() {
  const [downloads, setDownloads] = useState<Download[]>([])
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all')

  const loadData = async () => {
    try {
      const res = await api.getDownloads()
      setDownloads(res.downloads)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  // Smart polling while active downloads exist
  useEffect(() => {
    const hasActive = downloads.some((d) => d.status === 'downloading' || d.status === 'queued')
    if (!hasActive) return
    const interval = setInterval(loadData, 1500)
    return () => clearInterval(interval)
  }, [downloads])

  const visible = filterDownloads(downloads, activeFilter)

  return (
    <div>
      <PageHeader
        title="Downloads"
        description="Manage your active and past downloads"
        action={
          <button onClick={() => setFormOpen(true)} className="btn btn-primary btn-sm gap-2">
            <Plus className="w-3.5 h-3.5" />
            Add Download
          </button>
        }
      />

      {/* Filter tabs */}
      {!loading && downloads.length > 0 && (
        <div className="flex items-center gap-1 mb-5 p-1 rounded-xl w-fit" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
          {FILTERS.map((f) => {
            const count = filterCount(downloads, f.key)
            const isActive = activeFilter === f.key
            return (
              <button
                key={f.key}
                onClick={() => setActiveFilter(f.key)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-[var(--card-solid)] text-[var(--fg)] shadow-sm'
                    : 'text-[var(--muted)] hover:text-[var(--fg)]'
                }`}
              >
                <span className={isActive ? 'text-[var(--accent)]' : ''}>{f.icon}</span>
                {f.label}
                {count > 0 && (
                  <span
                    className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold leading-none"
                    style={{
                      background: isActive ? 'var(--accent-subtle)' : 'var(--border)',
                      color: isActive ? 'var(--accent)' : 'var(--muted)',
                    }}
                  >
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}

      {loading ? (
        <LoadingSpinner label="Loading downloads…" />
      ) : visible.length === 0 ? (
        <EmptyState
          title={activeFilter === 'all' ? 'No downloads yet' : `No ${activeFilter} downloads`}
          description={activeFilter === 'all' ? 'Add your first download to get started' : `You have no ${activeFilter} downloads right now`}
          icon={activeFilter === 'failed' ? XCircle : DownloadIcon}
          action={
            activeFilter === 'all' ? (
              <button onClick={() => setFormOpen(true)} className="btn btn-primary btn-sm gap-2">
                <Plus className="w-3.5 h-3.5" /> Add Download
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-2.5">
          <AnimatePresence mode="popLayout">
            {visible.map((dl) => (
              <DownloadCard key={dl.id} download={dl} onUpdated={loadData} />
            ))}
          </AnimatePresence>
        </div>
      )}

      <AddDownloadForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={loadData}
      />
    </div>
  )
}