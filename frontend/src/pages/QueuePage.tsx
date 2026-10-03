import { useEffect, useState } from 'react'
import { Play, Pause, X, RefreshCw, ChevronUp, ChevronDown, GripVertical, ListOrdered } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import StatusBadge from '../components/ui/StatusBadge'
import { formatBytes } from '../components/utils/formatters'
import type { QueueItem } from '../types'

export default function QueuePage() {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null)

  const loadData = async () => {
    try {
      const res = await api.getQueue()
      setQueue(res.queue)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  useEffect(() => {
    const hasActive = queue.some((q) => q.status === 'downloading' || q.status === 'queued')
    if (!hasActive) return
    const interval = setInterval(loadData, 1500)
    return () => clearInterval(interval)
  }, [queue])

  const moveItem = async (index: number, direction: 'up' | 'down') => {
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (targetIndex < 0 || targetIndex >= queue.length) return
    const newQueue = [...queue]
    const [moved] = newQueue.splice(index, 1)
    newQueue.splice(targetIndex, 0, moved)
    setQueue(newQueue)
    try {
      await api.reorderQueue(newQueue.map((item) => ({ id: item.id })))
    } catch {
      loadData()
    }
  }

  const handleDragOver = (e: React.DragEvent) => e.preventDefault()

  const handleDrop = async (targetIndex: number) => {
    if (draggedIndex === null || draggedIndex === targetIndex) return
    const newQueue = [...queue]
    const [moved] = newQueue.splice(draggedIndex, 1)
    newQueue.splice(targetIndex, 0, moved)
    setQueue(newQueue)
    setDraggedIndex(null)
    try {
      await api.reorderQueue(newQueue.map((item) => ({ id: item.id })))
    } catch {
      loadData()
    }
  }

  const handleAction = async (id: number, action: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove') => {
    try {
      switch (action) {
        case 'pause': await api.pauseDownload(id); break
        case 'resume': await api.resumeDownload(id); break
        case 'cancel': await api.cancelDownload(id); break
        case 'retry': await api.retryDownload(id); break
        case 'remove': await api.removeDownload(id); break
      }
      loadData()
    } catch (e) {
      console.error(e)
    }
  }

  const formatEta = (seconds?: number | null) => {
    if (!seconds) return '—'
    if (seconds < 60) return `${seconds}s`
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}m ${s}s`
  }

  return (
    <div>
      <PageHeader
        title="Queue"
        description="Manage your download queue and reorder pending tasks"
        action={
          queue.length > 0 ? (
            <span className="text-sm text-[var(--muted)] font-medium">{queue.length} item{queue.length !== 1 ? 's' : ''}</span>
          ) : undefined
        }
      />

      {loading ? (
        <LoadingSpinner label="Loading queue…" />
      ) : queue.length === 0 ? (
        <EmptyState
          icon={ListOrdered}
          title="Queue is empty"
          description="Downloads waiting to start will appear here"
        />
      ) : (
        <div className="card overflow-x-auto">
          <div className="min-w-[660px]">
            {/* Column headers */}
            <div
              className="grid items-center gap-4 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-widest text-[var(--muted)]"
            style={{
              gridTemplateColumns: '64px 1fr 100px 120px 80px 80px 100px',
              borderBottom: '1px solid var(--card-border)',
            }}
          >
            <span className="text-center">Order</span>
            <span>Title</span>
            <span>Quality</span>
            <span>Status</span>
            <span>Size</span>
            <span>ETA</span>
            <span className="text-right">Actions</span>
          </div>

          <AnimatePresence mode="popLayout">
            {queue.map((item, index) => (
              <motion.div
                key={item.id}
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: draggedIndex === index ? 0.4 : 1 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.15 }}
                draggable
                onDragStart={() => setDraggedIndex(index)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(index)}
                onDragEnd={() => setDraggedIndex(null)}
                className="grid items-center gap-4 px-4 py-3 hover:bg-[var(--bg-subtle)] transition-colors cursor-default"
                style={{
                  gridTemplateColumns: '64px 1fr 100px 120px 80px 80px 100px',
                  borderBottom: index < queue.length - 1 ? '1px solid var(--card-border)' : undefined,
                }}
              >
                {/* Order / drag */}
                <div className="flex items-center justify-center gap-1 text-[var(--muted)]">
                  <div className="flex flex-col">
                    <button
                      disabled={index === 0}
                      onClick={() => moveItem(index, 'up')}
                      className="p-0.5 hover:text-[var(--fg)] disabled:opacity-20 transition-colors"
                    >
                      <ChevronUp className="w-3 h-3" />
                    </button>
                    <button
                      disabled={index === queue.length - 1}
                      onClick={() => moveItem(index, 'down')}
                      className="p-0.5 hover:text-[var(--fg)] disabled:opacity-20 transition-colors"
                    >
                      <ChevronDown className="w-3 h-3" />
                    </button>
                  </div>
                  <span className="text-[11px] font-mono font-semibold w-4 text-center">{index + 1}</span>
                  <GripVertical className="w-3.5 h-3.5 opacity-40 hover:opacity-80 cursor-grab active:cursor-grabbing" />
                </div>

                {/* Title */}
                <p className="font-medium text-[13px] truncate">{item.title}</p>

                {/* Quality */}
                <span className="text-xs text-[var(--muted)] font-mono">{item.quality || 'best'}</span>

                {/* Status */}
                <StatusBadge status={item.status} />

                {/* Size */}
                <span className="text-xs text-[var(--muted)] font-mono">{formatBytes(item.total_size)}</span>

                {/* ETA */}
                <span className="text-xs text-[var(--muted)] font-mono">{formatEta(item.eta_seconds)}</span>

                {/* Actions */}
                <div className="flex justify-end gap-1">
                  {item.status === 'queued' && (
                    <>
                      <button
                        onClick={() => handleAction(item.download_id, 'pause')}
                        className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)] transition-colors"
                        title="Pause"
                      >
                        <Pause className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleAction(item.download_id, 'cancel')}
                        className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--danger)] hover:bg-[var(--danger-subtle)] transition-colors"
                        title="Cancel"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                  {item.status === 'downloading' && (
                    <button
                      onClick={() => handleAction(item.download_id, 'pause')}
                      className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)] transition-colors"
                      title="Pause"
                    >
                      <Pause className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {item.status === 'paused' && (
                    <>
                      <button
                        onClick={() => handleAction(item.download_id, 'resume')}
                        className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--success)] hover:bg-[var(--success-subtle)] transition-colors"
                        title="Resume"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleAction(item.download_id, 'cancel')}
                        className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--danger)] hover:bg-[var(--danger-subtle)] transition-colors"
                        title="Cancel"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                  {item.status === 'failed' && (
                    <button
                      onClick={() => handleAction(item.download_id, 'retry')}
                      className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors"
                      title="Retry"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  )
}