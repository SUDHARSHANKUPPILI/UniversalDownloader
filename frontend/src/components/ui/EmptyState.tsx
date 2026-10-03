import type { LucideIcon } from 'lucide-react'
import { InboxIcon } from 'lucide-react'

interface EmptyStateProps {
  title: string
  description: string
  icon?: LucideIcon
  action?: React.ReactNode
}

export default function EmptyState({ title, description, icon: Icon = InboxIcon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
        style={{
          background: 'var(--accent-soft)',
          border: '1px solid var(--border)',
          color: 'var(--muted)',
        }}
      >
        <Icon className="w-7 h-7" />
      </div>
      <h3 className="text-base font-semibold text-[var(--fg)]">{title}</h3>
      <p className="mt-1.5 text-sm text-[var(--muted)] max-w-xs leading-relaxed">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}