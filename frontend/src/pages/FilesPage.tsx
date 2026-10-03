import { useEffect, useState } from 'react'
import { File, Image, Music, Video, ExternalLink, FolderOpen, Trash2, HardDrive } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../services/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import EmptyState from '../components/ui/EmptyState'
import { formatBytes } from '../components/utils/formatters'
import { useNotifications } from '../components/hooks/useNotifications'

interface FileEntry {
  id: number
  filename: string
  media_type?: string
  size?: number
  path?: string
}

const TYPE_STYLES: Record<string, { icon: React.FC<{ className?: string }>, color: string, bg: string }> = {
  video: { icon: Video, color: '#60a5fa', bg: 'rgba(96,165,250,0.1)' },
  audio: { icon: Music, color: '#a78bfa', bg: 'rgba(167,139,250,0.1)' },
  image: { icon: Image, color: '#34d399', bg: 'rgba(52,211,153,0.1)' },
}

function getTypeStyle(media_type?: string) {
  return TYPE_STYLES[media_type ?? ''] ?? { icon: File, color: 'var(--muted)', bg: 'var(--bg-subtle)' }
}

export default function FilesPage() {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const { notify } = useNotifications()

  const loadData = async () => {
    try {
      const res = await api.getFiles()
      setFiles(res.files)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handleOpen = async (id: number, filename: string) => {
    try {
      await api.openFile(id)
      notify(`Opening ${filename}`)
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Failed to open file', 'error')
    }
  }

  const handleReveal = async (id: number) => {
    try {
      await api.revealFile(id)
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Failed to reveal in Explorer', 'error')
    }
  }

  const handleDelete = async (id: number, filename: string) => {
    try {
      await api.deleteFile(id)
      notify(`Deleted ${filename}`)
      loadData()
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Failed to delete file', 'error')
    }
  }

  const totalSize = files.reduce((acc, f) => acc + (f.size ?? 0), 0)

  return (
    <div>
      <PageHeader
        title="Files"
        description="Browse downloaded files and manage storage"
        action={
          files.length > 0 ? (
            <div className="flex items-center gap-1.5 text-sm text-[var(--muted)]">
              <HardDrive className="w-4 h-4" />
              <span className="font-mono font-medium">{formatBytes(totalSize)}</span>
              <span>· {files.length} file{files.length !== 1 ? 's' : ''}</span>
            </div>
          ) : undefined
        }
      />

      {loading ? (
        <LoadingSpinner label="Loading files…" />
      ) : files.length === 0 ? (
        <EmptyState
          icon={HardDrive}
          title="No files yet"
          description="Downloaded files will appear here when complete"
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {files.map((file, i) => {
            const { icon: Icon, color, bg } = getTypeStyle(file.media_type)
            return (
              <motion.div
                key={file.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="card p-4 group flex items-center gap-3 hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] transition-all duration-200"
              >
                {/* Type icon */}
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: bg, color }}
                >
                  <Icon className="w-5 h-5" />
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-[13px] truncate" title={file.filename}>{file.filename}</p>
                  <p className="text-[11px] text-[var(--muted)] mt-0.5">
                    <span className="capitalize">{file.media_type || 'file'}</span>
                    {file.size ? <span className="font-mono ml-1.5">{formatBytes(file.size)}</span> : null}
                  </p>
                </div>

                {/* Actions — reveal on hover */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex-shrink-0">
                  <button
                    onClick={() => handleOpen(file.id, file.filename)}
                    className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)] transition-colors"
                    title="Open file"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleReveal(file.id)}
                    className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--card-hover)] transition-colors"
                    title="Reveal in Explorer"
                  >
                    <FolderOpen className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(file.id, file.filename)}
                    className="p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--danger)] hover:bg-[var(--danger-subtle)] transition-colors"
                    title="Delete file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}