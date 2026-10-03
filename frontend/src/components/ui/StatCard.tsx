import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  accent?: string
  description?: string
}

export default function StatCard({ label, value, icon: Icon, accent, description }: StatCardProps) {
  const color = accent || 'var(--accent)'
  const bg = `color-mix(in srgb, ${color} 12%, transparent)`
  const border = `color-mix(in srgb, ${color} 22%, transparent)`

  return (
    <div className="card p-5 shadow-subtle group transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-medium)]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-transform duration-200 group-hover:scale-110"
          style={{ background: bg, color, border: `1px solid ${border}` }}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-[28px] font-bold tracking-tight text-[var(--fg)] leading-none">{value}</p>
      {description && (
        <p className="mt-1.5 text-xs text-[var(--muted)]">{description}</p>
      )}
      {/* Bottom accent strip */}
      <div
        className="mt-4 h-[2px] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ background: `linear-gradient(90deg, ${color}, transparent)` }}
      />
    </div>
  )
}
