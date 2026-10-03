import { Play, Pause, RotateCcw, Trash2, X, FileVideo, FileAudio } from 'lucide-react'
import { motion } from 'framer-motion'
import type { Download } from '../../types'
import ProgressBar from '../ui/ProgressBar'
import StatusBadge from '../ui/StatusBadge'
import { api } from '../../services/api'
import { useNotifications } from '../hooks/useNotifications'
import { formatBytes } from '../utils/formatters'

interface DownloadCardProps {
  download: Download
  onUpdated: () => void
}

const STATUS_COLORS: Record<string, string> = {
  downloading: 'var(--info)',
  queued: 'var(--warning)',
  paused: 'var(--warning)',
  completed: 'var(--success)',
  failed: 'var(--danger)',
  cancelled: 'var(--muted)',
}

export default function DownloadCard({ download, onUpdated }: DownloadCardProps) {
  const { notify } = useNotifications()
  const statusColor = STATUS_COLORS[download.status] ?? 'var(--muted)'

  const handleAction = async (action: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove') => {
    try {
      switch (action) {
        case 'pause': await api.pauseDownload(download.id); break
        case 'resume': await api.resumeDownload(download.id); break
        case 'cancel': await api.cancelDownload(download.id); break
        case 'retry': await api.retryDownload(download.id); break
        case 'remove': await api.removeDownload(download.id); notify('Download removed'); onUpdated(); return
      }
      onUpdated()
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Action failed', 'error')
    }
  }

  const MediaIcon = download.media_type === 'audio' ? FileAudio : FileVideo

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="card overflow-hidden"
      style={{
        borderLeft: `3px solid ${statusColor}`,
        paddingLeft: 0,
      }}
    >
      <div className="flex items-start gap-4 p-4 pl-5">
        {/* Icon badge */}
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{
            background: `color-mix(in srgb, ${statusColor} 12%, transparent)`,
            border: `1px solid color-mix(in srgb, ${statusColor} 22%, transparent)`,
            color: statusColor,
          }}
        >
          <MediaIcon className="w-5 h-5" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-semibold text-[14px] leading-snug truncate" title={download.title}>
              {download.title}
            </h3>
            <div className="flex items-center gap-2 flex-shrink-0">
              <StatusBadge status={download.status} />
            </div>
          </div>

          {/* Meta row */}
          <div className="flex items-center gap-2 mt-1 text-xs text-[var(--muted)]">
            <span className="capitalize">
              {download.media_type === 'audio' ? 'Audio' : download.media_type === 'playlist' ? 'Playlist' : 'Video'}
            </span>
            <span className="text-[var(--border-strong)]">·</span>
            <span>{download.quality || 'best'}</span>
            {download.total_size ? (
              <>
                <span className="text-[var(--border-strong)]">·</span>
                <span className="font-mono">{formatBytes(download.total_size)}</span>
              </>
            ) : null}
          </div>

          {/* Progress */}
          {download.status === 'downloading' && (
            <div className="mt-3 space-y-1.5">
              <ProgressBar value={download.progress || 0} max={100} />
              <div className="flex items-center justify-between text-[11px] text-[var(--muted)]">
                <span className="font-mono">
                  {formatBytes(download.downloaded_size || 0)} / {formatBytes(download.total_size || 0)}
                </span>
                <div className="flex items-center gap-3">
                  {download.speed ? (
                    <span className="font-mono text-[var(--info)]">
                      {(download.speed / 1024).toFixed(1)} KB/s
                    </span>
                  ) : null}
                  <span className="font-medium text-[var(--accent)]">{download.progress}%</span>
                </div>
              </div>
            </div>
          )}

          {/* Error message */}
          {download.error_message && (
            <p className="mt-2 text-xs text-[var(--danger)] bg-[var(--danger-subtle)] px-2.5 py-1.5 rounded-lg border border-[color-mix(in_srgb,var(--danger)_20%,transparent)]">
              {download.error_message}
            </p>
          )}

          {/* Actions */}
          <div className="flex items-center gap-1.5 mt-3">
            {download.status === 'downloading' && (
              <button
                onClick={() => handleAction('pause')}
                className="btn btn-secondary btn-sm gap-1.5"
                title="Pause download"
              >
                <Pause className="w-3 h-3" /> Pause
              </button>
            )}
            {download.status === 'paused' && (
              <button
                onClick={() => handleAction('resume')}
                className="btn btn-secondary btn-sm gap-1.5"
                title="Resume download"
              >
                <Play className="w-3 h-3" /> Resume
              </button>
            )}
            {(download.status === 'failed' || download.status === 'paused') && (
              <button
                onClick={() => handleAction('retry')}
                className="btn btn-secondary btn-sm gap-1.5"
                title="Retry download"
              >
                <RotateCcw className="w-3 h-3" /> Retry
              </button>
            )}
            {(download.status === 'queued' || download.status === 'downloading') && (
              <button
                onClick={() => handleAction('cancel')}
                className="btn btn-danger btn-sm gap-1.5"
                title="Cancel download"
              >
                <X className="w-3 h-3" /> Cancel
              </button>
            )}
            {/* Remove always available for terminal states */}
            {(download.status === 'completed' || download.status === 'failed' || download.status === 'cancelled') && (
              <button
                onClick={() => handleAction('remove')}
                className="btn btn-ghost btn-sm gap-1.5 text-[var(--muted)]"
                title="Remove from list"
              >
                <Trash2 className="w-3 h-3" /> Remove
              </button>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}