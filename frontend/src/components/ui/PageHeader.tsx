import React from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  action?: React.ReactNode
}

export default function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-7">
      <div>
        <h1 className="text-[22px] font-bold tracking-tight text-[var(--fg)]">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-[var(--muted)] leading-relaxed">{description}</p>
        )}
      </div>
      {action && (
        <div className="flex-shrink-0 pt-0.5">{action}</div>
      )}
    </div>
  )
}