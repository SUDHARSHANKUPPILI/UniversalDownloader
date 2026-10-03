import React, { useEffect, useState } from 'react'
import { Save, RotateCcw, Settings as SettingsIcon, Sliders } from 'lucide-react'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import { useNotifications } from '../components/hooks/useNotifications'
import type { Settings } from '../types'

const BOOLEAN_KEYS: (keyof Settings)[] = [
  'auto_embed_subtitles',
  'auto_organize',
  'duplicate_detection',
  'notifications',
  'retry_enabled',
  'embed_metadata',
  'embed_thumbnail',
]

const KEY_LABELS: Partial<Record<keyof Settings, string>> = {
  auto_embed_subtitles: 'Auto-embed subtitles',
  auto_organize: 'Auto-organize files',
  duplicate_detection: 'Duplicate detection',
  notifications: 'Notifications',
  retry_enabled: 'Auto-retry on failure',
  embed_metadata: 'Embed metadata',
  embed_thumbnail: 'Embed thumbnail',
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative flex-shrink-0 w-10 h-[22px] rounded-full transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
      style={{
        background: checked ? 'var(--accent)' : 'var(--border)',
      }}
    >
      <span
        className="absolute top-[3px] left-[3px] w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200"
        style={{ transform: checked ? 'translateX(18px)' : 'translateX(0)' }}
      />
    </button>
  )
}

function Section({ title, icon: Icon, children }: { title: string; icon: React.FC<{ className?: string }>; children: React.ReactNode }) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2.5 px-5 py-4" style={{ borderBottom: '1px solid var(--card-border)' }}>
        <Icon className="w-4 h-4 text-[var(--accent)]" />
        <h3 className="font-semibold text-[14px]">{title}</h3>
      </div>
      <div className="px-5 py-4 space-y-5">{children}</div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2.5 sm:gap-6">
      <div className="min-w-0 flex-1">
        <label className="block text-[13px] font-medium text-[var(--fg)]">{label}</label>
        {hint && <p className="text-[11px] text-[var(--muted)] mt-0.5 leading-snug">{hint}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  )
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { notify } = useNotifications()

  const loadData = async () => {
    try {
      const res = await api.getSettings()
      setSettings(res)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const set = (key: keyof Settings, value: string) =>
    setSettings((prev) => prev ? { ...prev, [key]: value } : prev)

  const setBool = (key: keyof Settings, value: boolean) =>
    set(key, value ? 'true' : 'false')

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!settings) return
    setSaving(true)
    try {
      await api.updateSettings(settings)
      notify('Settings saved successfully')
    } catch {
      notify('Failed to save settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader title="Settings" description="Configure application preferences" />

      {loading ? (
        <LoadingSpinner label="Loading settings…" />
      ) : (
        <form onSubmit={handleSave} className="max-w-2xl space-y-5">
        {/* General */}
        <Section title="General" icon={SettingsIcon}>
          <Field label="Max concurrent downloads" hint="Number of downloads to run simultaneously">
            <input
              type="number"
              min="1"
              max="16"
              value={settings?.max_concurrency ?? ''}
              onChange={(e) => set('max_concurrency', e.target.value)}
              className="input w-24 text-center"
            />
          </Field>
          <div style={{ borderTop: '1px solid var(--card-border)' }} />
          <Field label="Default quality" hint="Quality preference for new downloads">
            <select
              value={settings?.default_quality ?? 'best'}
              onChange={(e) => set('default_quality', e.target.value)}
              className="input w-36"
            >
              <option value="best">Best</option>
              <option value="2160p">4K (2160p)</option>
              <option value="1440p">1440p</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
              <option value="audio">Audio Only</option>
            </select>
          </Field>
          <div style={{ borderTop: '1px solid var(--card-border)' }} />
          <Field label="Save location" hint="Default folder for downloaded files">
            <input
              type="text"
              value={settings?.save_location ?? ''}
              onChange={(e) => set('save_location', e.target.value)}
              className="input w-full sm:w-64"
              placeholder="/path/to/downloads"
            />
          </Field>
          <div style={{ borderTop: '1px solid var(--card-border)' }} />
          <Field label="Bandwidth limit" hint="0 = unlimited (bytes per second)">
            <input
              type="number"
              min="0"
              value={settings?.bandwidth_limit ?? ''}
              onChange={(e) => set('bandwidth_limit', e.target.value)}
              className="input w-32 text-center font-mono"
            />
          </Field>
          <div style={{ borderTop: '1px solid var(--card-border)' }} />
          <Field label="Max retries" hint="Retry attempts on download failure">
            <input
              type="number"
              min="0"
              value={settings?.max_retries ?? ''}
              onChange={(e) => set('max_retries', e.target.value)}
              className="input w-24 text-center"
            />
          </Field>
          <div style={{ borderTop: '1px solid var(--card-border)' }} />
          <Field label="Subtitle languages" hint="Comma-separated language codes (e.g. en,es,fr)">
            <input
              type="text"
              value={settings?.subtitle_languages ?? ''}
              onChange={(e) => set('subtitle_languages', e.target.value)}
              className="input w-full sm:w-48 font-mono"
              placeholder="en,es,fr"
            />
          </Field>
        </Section>

        {/* Behaviour toggles */}
        <Section title="Behaviour" icon={Sliders}>
          {BOOLEAN_KEYS.map((key, i) => (
            <React.Fragment key={key}>
              {i > 0 && <div style={{ borderTop: '1px solid var(--card-border)' }} />}
              <Field label={KEY_LABELS[key] ?? key}>
                <Toggle
                  checked={settings?.[key] === 'true'}
                  onChange={(v) => setBool(key, v)}
                />
              </Field>
            </React.Fragment>
          ))}
        </Section>

        {/* Appearance */}
        <Section title="Appearance" icon={Sliders}>
          <Field label="Theme" hint="Application color theme">
            <select
              value={settings?.theme ?? 'dark'}
              onChange={(e) => set('theme', e.target.value)}
              className="input w-36"
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="system">System</option>
            </select>
          </Field>
        </Section>

        {/* Actions */}
        <div className="flex gap-2.5 pt-1">
          <button type="submit" disabled={saving} className="btn btn-primary gap-2">
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
          <button type="button" onClick={loadData} disabled={saving} className="btn btn-secondary gap-2">
            <RotateCcw className="w-4 h-4" />
            Reset
          </button>
        </div>
      </form>
      )}
    </div>
  )
}