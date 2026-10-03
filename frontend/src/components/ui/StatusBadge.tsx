import { CheckCircle2, Download, PauseCircle, XCircle, Clock } from 'lucide-react'

export default function StatusBadge({ status }: { status: string }) {
  const normalized = status?.toLowerCase() || ''
  const statusConfig: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
    queued: {
      label: 'Queued',
      className: 'bg-[var(--warning-subtle)] text-[var(--warning)] border-[color-mix(in_srgb,var(--warning)_25%,transparent)]',
      icon: <Clock className="w-3 h-3" />,
    },
    downloading: {
      label: 'Downloading',
      className: 'bg-[var(--info-subtle)] text-[var(--info)] border-[color-mix(in_srgb,var(--info)_25%,transparent)]',
      icon: <Download className="w-3 h-3" />,
    },
    paused: {
      label: 'Paused',
      className: 'bg-[var(--warning-subtle)] text-[var(--warning)] border-[color-mix(in_srgb,var(--warning)_25%,transparent)]',
      icon: <PauseCircle className="w-3 h-3" />,
    },
    completed: {
      label: 'Completed',
      className: 'bg-[var(--success-subtle)] text-[var(--success)] border-[color-mix(in_srgb,var(--success)_25%,transparent)]',
      icon: <CheckCircle2 className="w-3 h-3" />,
    },
    failed: {
      label: 'Failed',
      className: 'bg-[var(--danger-subtle)] text-[var(--danger)] border-[color-mix(in_srgb,var(--danger)_25%,transparent)]',
      icon: <XCircle className="w-3 h-3" />,
    },
    cancelled: {
      label: 'Cancelled',
      className: 'bg-[var(--card-hover)] text-[var(--muted)] border-[var(--border)]',
      icon: <XCircle className="w-3 h-3" />,
    },
  }

  const config = statusConfig[normalized] || {
    label: status || 'Unknown',
    className: 'bg-[var(--card-hover)] text-[var(--muted)] border-[var(--border)]',
    icon: null,
  }

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${config.className}`}>
      {config.icon}
      {config.label}
    </span>
  )
}