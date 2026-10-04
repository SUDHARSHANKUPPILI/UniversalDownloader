import React, { useState } from 'react'
import { Plus, Loader2 } from 'lucide-react'
import { api } from '../../services/api'
import { useNotifications } from '../hooks/useNotifications'
import { Modal } from '../ui'

interface AddDownloadFormProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export default function AddDownloadForm({ open, onClose, onSuccess }: AddDownloadFormProps) {
  const [url, setUrl] = useState('')
  const [quality, setQuality] = useState('best')
  const [format, setFormat] = useState('bestvideo+bestaudio')
  const [subtitleLanguages, setSubtitleLanguages] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [analysis, setAnalysis] = useState<null | { valid: boolean; title?: string; uploader?: string; duration?: number; thumbnail?: string; is_playlist?: boolean; playlist_count?: number; error?: string }>(null)
  const { notify } = useNotifications()

  const handleAnalyze = async () => {
    if (!url.trim()) return
    setAnalyzing(true)
    setAnalysis(null)
    try {
      const result = await api.analyzeUrl(url.trim())
      setAnalysis(result)
      if (!result.valid) {
        notify(result.error || 'Analysis failed', 'error')
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Analysis failed', 'error')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    setSubmitting(true)
    try {
      const result = await api.createDownload({
        url: url.trim(),
        quality,
        format,
        subtitle_languages: subtitleLanguages.trim()
          ? subtitleLanguages.split(',').map(s => s.trim()).filter(Boolean)
          : undefined,
      })
      if (result.success) {
        notify(`Added: ${result.title}`)
        setUrl('')
        setAnalysis(null)
        setSubtitleLanguages('')
        onClose()
        onSuccess()
      } else {
        notify('Failed to create download', 'error')
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Failed to create download', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return ''
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    return h > 0 ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}` : `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <Modal open={open} onClose={onClose} title="Add New Download">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1.5">URL</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
              className="input flex-1"
              disabled={submitting}
            />
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={analyzing || !url.trim()}
              className="btn btn-secondary whitespace-nowrap"
            >
              {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Analyze'}
            </button>
          </div>
        </div>

        {analysis && analysis.valid && (
          <div className="flex gap-3 p-3 rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)]">
            {analysis.thumbnail && (
              <img src={analysis.thumbnail} alt="" className="w-20 h-12 object-cover rounded" />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">{analysis.title || 'Unknown'}</p>
              <p className="text-xs text-[var(--muted)]">
                {analysis.uploader && `${analysis.uploader} • `}
                {formatDuration(analysis.duration)}
                {analysis.is_playlist && ` • Playlist (${analysis.playlist_count} videos)`}
              </p>
            </div>
          </div>
        )}

        {analysis && !analysis.valid && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
            {analysis.error || 'Invalid URL'}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1.5">Quality</label>
            <select
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              className="input"
              disabled={submitting}
            >
              <option value="best">Best</option>
              <option value="2160p">4K (2160p)</option>
              <option value="1440p">1440p</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
              <option value="audio">Audio Only</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">Format</label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              className="input"
              disabled={submitting}
            >
              <option value="bestvideo+bestaudio">Video + Audio</option>
              <option value="best">Best (Single)</option>
              <option value="bestaudio/best">Audio Only</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1.5">Subtitle Languages</label>
          <input
            type="text"
            value={subtitleLanguages}
            onChange={(e) => setSubtitleLanguages(e.target.value)}
            placeholder="en,es,fr (comma-separated)"
            className="input"
            disabled={submitting}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="btn btn-secondary" disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting || !url.trim() || (analysis ? !analysis.valid : false)}>
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Add Download
          </button>
        </div>
      </form>
    </Modal>
  )
}