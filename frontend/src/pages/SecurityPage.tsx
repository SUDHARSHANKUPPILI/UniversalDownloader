import { useEffect, useState } from 'react'
import { Shield, ShieldAlert, AlertTriangle, AlertCircle, Info, RefreshCw, Filter } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import StatCard from '../components/ui/StatCard'
import { formatRelativeTime } from '../components/utils/formatters'
import type { SecurityEvent } from '../types'

type SeverityFilter = 'all' | 'critical' | 'warning' | 'info'

function formatEventType(type: string): string {
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function SecurityPage() {
  const [events, setEvents] = useState<SecurityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<SeverityFilter>('all')

  const loadData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true)
    try {
      const res = await api.getSecurityEvents(100)
      setEvents((res as unknown) as SecurityEvent[])
    } catch (e) {
      console.error('Failed to load security events', e)
    } finally {
      setLoading(false)
      if (isManualRefresh) setRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const criticalCount = events.filter((e) => e.severity === 'critical').length
  const warningCount = events.filter((e) => e.severity === 'warning').length
  const infoCount = events.filter((e) => e.severity !== 'critical' && e.severity !== 'warning').length

  const filteredEvents = events.filter((e) => {
    if (filter === 'critical') return e.severity === 'critical'
    if (filter === 'warning') return e.severity === 'warning'
    if (filter === 'info') return e.severity !== 'critical' && e.severity !== 'warning'
    return true
  })

  const getSeverityBadge = (severity: string) => {
    const s = severity?.toLowerCase()
    if (s === 'critical') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-[var(--danger-subtle)] text-[var(--danger)] border border-[color-mix(in_srgb,var(--danger)_30%,transparent)]">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          Critical
        </span>
      )
    }
    if (s === 'warning') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-[var(--warning-subtle)] text-[var(--warning)] border border-[color-mix(in_srgb,var(--warning)_30%,transparent)]">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          Warning
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-[var(--info-subtle)] text-[var(--info)] border border-[color-mix(in_srgb,var(--info)_30%,transparent)]">
        <Info className="w-3.5 h-3.5 flex-shrink-0" />
        Info
      </span>
    )
  }

  return (
    <div>
      <PageHeader
        title="Security"
        description="Audit center, access logs, and anomaly detection"
        action={
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="btn btn-secondary btn-sm gap-2"
            title="Refresh security log"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      {/* Real Summary Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Total Audited Events"
          value={events.length}
          icon={Shield}
          accent="var(--accent)"
        />
        <StatCard
          label="Critical Threats"
          value={criticalCount}
          icon={ShieldAlert}
          accent="#f87171"
        />
        <StatCard
          label="Warnings"
          value={warningCount}
          icon={AlertTriangle}
          accent="#fbbf24"
        />
        <StatCard
          label="Informational"
          value={infoCount}
          icon={Info}
          accent="#60a5fa"
        />
      </div>

      {/* Filter Tabs */}
      {!loading && events.length > 0 && (
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-1 p-1 rounded-xl w-fit" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
            {[
              { id: 'all' as SeverityFilter, label: 'All Events', count: events.length },
              { id: 'critical' as SeverityFilter, label: 'Critical', count: criticalCount },
              { id: 'warning' as SeverityFilter, label: 'Warnings', count: warningCount },
              { id: 'info' as SeverityFilter, label: 'Info', count: infoCount },
            ].map((tab) => {
              const isActive = filter === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setFilter(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-[var(--card-solid)] text-[var(--fg)] shadow-sm'
                      : 'text-[var(--muted)] hover:text-[var(--fg)]'
                  }`}
                >
                  <span>{tab.label}</span>
                  <span
                    className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-semibold"
                    style={{
                      background: isActive ? 'var(--accent-subtle)' : 'var(--border)',
                      color: isActive ? 'var(--accent)' : 'var(--muted)',
                    }}
                  >
                    {tab.count}
                  </span>
                </button>
              )
            })}
          </div>
          <span className="text-xs text-[var(--muted)]">
            Showing {filteredEvents.length} of {events.length} events
          </span>
        </div>
      )}

      {/* Events Table / State */}
      {loading ? (
        <LoadingSpinner label="Auditing security events…" />
      ) : events.length === 0 ? (
        <EmptyState
          icon={Shield}
          title="No security events recorded"
          description="System activity is clean. No policy violations or anomalous attempts detected."
        />
      ) : filteredEvents.length === 0 ? (
        <EmptyState
          icon={Filter}
          title={`No ${filter} events`}
          description={`There are currently no events matching the "${filter}" severity level.`}
        />
      ) : (
        <div className="card overflow-x-auto">
          <div className="min-w-[620px]">
            <div
              className="grid items-center gap-4 px-5 py-3 text-[11px] font-semibold uppercase tracking-widest text-[var(--muted)]"
            style={{
              gridTemplateColumns: '110px 180px 1fr 140px',
              borderBottom: '1px solid var(--card-border)',
            }}
          >
            <span>Severity</span>
            <span>Event Type</span>
            <span>Details & Source</span>
            <span className="text-right">Time</span>
          </div>

          <AnimatePresence mode="popLayout">
            {filteredEvents.map((evt, i) => (
              <motion.div
                key={evt.id || i}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="grid items-center gap-4 px-5 py-3.5 hover:bg-[var(--bg-subtle)] transition-colors"
                style={{
                  gridTemplateColumns: '110px 180px 1fr 140px',
                  borderBottom: i < filteredEvents.length - 1 ? '1px solid var(--card-border)' : undefined,
                }}
              >
                {/* Severity Badge */}
                <div>{getSeverityBadge(evt.severity)}</div>

                {/* Event Type */}
                <div className="min-w-0">
                  <span className="text-[13px] font-semibold text-[var(--fg)] truncate block">
                    {formatEventType(evt.event_type || 'Unknown')}
                  </span>
                  <span className="text-[11px] font-mono text-[var(--muted)]">
                    {evt.event_type}
                  </span>
                </div>

                {/* Description & Metadata */}
                <div className="min-w-0 pr-2">
                  <p className="text-[13px] text-[var(--fg)] leading-relaxed line-clamp-2">
                    {evt.description}
                  </p>
                  {(evt.ip_address || evt.url) && (
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {evt.ip_address && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-[var(--bg-subtle)] text-[var(--muted)] border border-[var(--border)]">
                          IP: {evt.ip_address}
                        </span>
                      )}
                      {evt.url && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-[var(--bg-subtle)] text-[var(--muted)] border border-[var(--border)] truncate max-w-sm" title={evt.url}>
                          URL: {evt.url}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Time */}
                <div className="text-right flex-shrink-0">
                  <p className="text-xs font-medium text-[var(--fg)]" title={evt.created_at}>
                    {formatRelativeTime(evt.created_at)}
                  </p>
                  <p className="text-[10px] text-[var(--muted)] font-mono mt-0.5">
                    {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ''}
                  </p>
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