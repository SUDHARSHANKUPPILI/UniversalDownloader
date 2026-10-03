export default function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const percentage = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="progress-bar">
      <div
        className="progress-fill bg-[var(--accent)]"
        style={{ width: `${percentage}%` }}
      />
    </div>
  )
}