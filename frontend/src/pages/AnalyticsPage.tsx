import { useEffect, useState } from 'react'
import { BarChart3, Download, TrendingUp } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import { StatCard } from '../components/ui'
import { formatNumber, formatBytes } from '../components/utils/formatters'

interface AnalyticsData {
  daily: Array<{ day: string; count: number }>
  monthly: Array<{ month: string; total: number; completed: number }>
  total_downloads: number
  total_size: number
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getAnalytics()
      .then((res) => setData(res))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner label="Loading analytics…" />

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Download statistics and activity trends"
      />

      {data ? (
        <div className="space-y-6">
          {/* Summary stat cards */}
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Total Downloads"
              value={formatNumber(data.total_downloads ?? 0)}
              icon={Download}
              accent="#60a5fa"
            />
            <StatCard
              label="Total Data Downloaded"
              value={formatBytes(data.total_size ?? 0)}
              icon={TrendingUp}
              accent="#34d399"
            />
          </div>

          {/* Daily activity chart */}
          {data.daily && data.daily.length > 0 && (
            <div className="card p-5">
              <h2 className="font-semibold text-[15px] mb-5">Daily Activity — Last 30 Days</h2>
              <DailyChart daily={data.daily} />
            </div>
          )}

          {/* Monthly breakdown */}
          {data.monthly && data.monthly.length > 0 && (
            <div className="card p-5">
              <h2 className="font-semibold text-[15px] mb-5">Monthly Success Rate</h2>
              <MonthlyChart monthly={data.monthly} />
            </div>
          )}

          {(!data.daily || data.daily.length === 0) && (!data.monthly || data.monthly.length === 0) && (
            <EmptyState
              icon={BarChart3}
              title="No activity data yet"
              description="Charts will appear as you complete downloads"
            />
          )}
        </div>
      ) : (
        <EmptyState
          icon={BarChart3}
          title="No analytics data"
          description="Analytics will appear after you start downloading"
        />
      )}
    </div>
  )
}

function DailyChart({ daily }: { daily: AnalyticsData['daily'] }) {
  const maxCount = Math.max(...daily.map((d) => d.count), 1)

  return (
    <div className="flex items-end gap-1" style={{ height: 160 }}>
      {daily.map((d, i) => {
        const heightPct = (d.count / maxCount) * 100
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative" title={`${d.day}: ${d.count}`}>
            {/* Tooltip */}
            {d.count > 0 && (
              <div className="absolute bottom-full mb-1.5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                <div
                  className="px-2 py-1 rounded-lg text-[11px] font-semibold whitespace-nowrap"
                  style={{ background: 'var(--glass-strong)', border: '1px solid var(--border)', color: 'var(--fg)' }}
                >
                  {d.count} · {d.day.slice(5)}
                </div>
              </div>
            )}
            {/* Bar */}
            <motion.div
              className="w-full rounded-t"
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(heightPct, d.count > 0 ? 4 : 2)}%` }}
              transition={{ delay: i * 0.01, duration: 0.4, ease: 'easeOut' }}
              style={{
                background: d.count > 0
                  ? 'linear-gradient(180deg, var(--accent) 0%, var(--accent-subtle) 100%)'
                  : 'var(--border)',
                alignSelf: 'flex-end',
                minHeight: 2,
              }}
            />
          </div>
        )
      })}
    </div>
  )
}

function MonthlyChart({ monthly }: { monthly: AnalyticsData['monthly'] }) {
  const maxTotal = Math.max(...monthly.map((m) => m.total), 1)

  return (
    <div className="space-y-3">
      {monthly.map((m, i) => {
        const totalPct = (m.total / maxTotal) * 100
        const successPct = m.total > 0 ? (m.completed / m.total) * 100 : 0
        return (
          <div key={i} className="flex items-center gap-4">
            <span className="text-[12px] text-[var(--muted)] font-mono w-16 flex-shrink-0">{m.month}</span>
            <div className="flex-1 relative h-6 rounded-lg overflow-hidden" style={{ background: 'var(--bg-subtle)' }}>
              {/* Total bar */}
              <motion.div
                className="absolute inset-y-0 left-0 rounded-lg"
                initial={{ width: 0 }}
                animate={{ width: `${totalPct}%` }}
                transition={{ delay: i * 0.06, duration: 0.5, ease: 'easeOut' }}
                style={{ background: 'var(--border)' }}
              />
              {/* Success bar */}
              <motion.div
                className="absolute inset-y-0 left-0 rounded-lg"
                initial={{ width: 0 }}
                animate={{ width: `${(successPct / 100) * totalPct}%` }}
                transition={{ delay: i * 0.06 + 0.15, duration: 0.5, ease: 'easeOut' }}
                style={{ background: 'linear-gradient(90deg, var(--success), color-mix(in srgb, var(--success) 60%, transparent))' }}
              />
            </div>
            <span className="text-[12px] text-[var(--muted)] font-mono w-20 text-right flex-shrink-0">
              {m.completed}/{m.total}
            </span>
          </div>
        )
      })}
    </div>
  )
}
