import { useEffect, useRef } from 'react'
import { api } from '../services/api'
import { useNotifications } from '../components/hooks/useNotifications'
import { sendDesktopNotification } from '../utils/notifications'

const NOTIFIED_STORAGE_KEY = 'ud_notified_downloads'
const DESKTOP_STORAGE_KEY = 'ud_desktop_notifications'

function getNotifiedMap(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(NOTIFIED_STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveNotifiedMap(map: Record<string, string>) {
  if (typeof window === 'undefined') return
  try {
    // Keep map size bounded to the latest 500 entries to avoid localStorage bloat
    const keys = Object.keys(map)
    if (keys.length > 500) {
      const trimmed: Record<string, string> = {}
      for (const k of keys.slice(-400)) {
        trimmed[k] = map[k]
      }
      localStorage.setItem(NOTIFIED_STORAGE_KEY, JSON.stringify(trimmed))
      return
    }
    localStorage.setItem(NOTIFIED_STORAGE_KEY, JSON.stringify(map))
  } catch {
    // Ignore storage write issues
  }
}

export function getDownloadFilename(d: { id: number; title?: string | null; output_path?: string | null }): string {
  if (d.output_path && typeof d.output_path === 'string') {
    const parts = d.output_path.split(/[/\\]/)
    const last = parts[parts.length - 1]
    if (last && last.trim()) return last.trim()
  }
  return d.title || `Download #${d.id}`
}

export function useDownloadNotifications() {
  const { notify } = useNotifications()
  const initializedRef = useRef(false)
  const prevActiveOrQueuedRef = useRef<number | null>(null)
  const isPollingRef = useRef(false)

  useEffect(() => {
    let unmounted = false

    const checkDownloads = async () => {
      if (isPollingRef.current) return
      isPollingRef.current = true

      try {
        const [downloadsRes, settingsRes] = await Promise.all([
          api.getDownloads().catch(() => null),
          api.getSettings().catch(() => null),
        ])

        if (unmounted || !downloadsRes?.downloads) return

        const downloads = downloadsRes.downloads
        const notificationsEnabled = settingsRes?.notifications !== 'false'
        const desktopEnabled = typeof window !== 'undefined' && localStorage.getItem(DESKTOP_STORAGE_KEY) === 'true'
        const notifiedMap = getNotifiedMap()

        const activeOrQueued = downloads.filter(
          (d) => d.status === 'downloading' || d.status === 'queued'
        ).length

        // First run on mount / page refresh:
        // Seed any downloads already in terminal states so we don't alert for past events.
        if (!initializedRef.current) {
          let updated = false
          for (const d of downloads) {
            const idStr = String(d.id)
            if ((d.status === 'completed' || d.status === 'failed' || d.status === 'cancelled') && !notifiedMap[idStr]) {
              notifiedMap[idStr] = d.status
              updated = true
            }
          }
          if (updated) {
            saveNotifiedMap(notifiedMap)
          }
          prevActiveOrQueuedRef.current = activeOrQueued
          initializedRef.current = true
          return
        }

        // Subsequent polling cycles
        let mapModified = false

        for (const d of downloads) {
          const idStr = String(d.id)
          const prevNotifiedStatus = notifiedMap[idStr]

          if (d.status === 'completed' && prevNotifiedStatus !== 'completed') {
            notifiedMap[idStr] = 'completed'
            mapModified = true

            if (notificationsEnabled) {
              const filename = getDownloadFilename(d)
              const msg = `Download completed: ${filename}`
              notify(msg, 'success')
              if (desktopEnabled) {
                sendDesktopNotification('UniversalDownloader', { body: msg, icon: '/favicon.svg' })
              }
            }
          } else if (d.status === 'failed' && prevNotifiedStatus !== 'failed') {
            notifiedMap[idStr] = 'failed'
            mapModified = true

            if (notificationsEnabled) {
              const filename = getDownloadFilename(d)
              const msg = `Download failed: ${filename}`
              notify(msg, 'error')
              if (desktopEnabled) {
                sendDesktopNotification('UniversalDownloader', { body: msg, icon: '/favicon.svg' })
              }
            }
          }
        }

        if (mapModified) {
          saveNotifiedMap(notifiedMap)
        }

        // Queue completion notification
        if (
          prevActiveOrQueuedRef.current !== null &&
          prevActiveOrQueuedRef.current > 0 &&
          activeOrQueued === 0
        ) {
          if (notificationsEnabled) {
            const queueMsg = 'Download queue completed'
            notify(queueMsg, 'success')
            if (desktopEnabled) {
              sendDesktopNotification('UniversalDownloader', { body: queueMsg, icon: '/favicon.svg' })
            }
          }
        }

        prevActiveOrQueuedRef.current = activeOrQueued
      } catch {
        // Silently tolerate transient network errors
      } finally {
        isPollingRef.current = false
      }
    }

    // Initial check
    checkDownloads()

    // Smart polling timer (2.5s)
    const interval = setInterval(checkDownloads, 2500)

    return () => {
      unmounted = true
      clearInterval(interval)
    }
  }, [notify])
}
