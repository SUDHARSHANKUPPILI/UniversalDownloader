import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'

type NotificationType = 'success' | 'error'

interface Notification {
  id: number
  message: string
  type: NotificationType
}

interface NotificationContextValue {
  notifications: Notification[]
  notify: (message: string, type?: NotificationType) => void
  dismiss: (id: number) => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])

  const dismiss = useCallback((id: number) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  const notify = useCallback((message: string, type: NotificationType = 'success') => {
    const id = Date.now() + Math.random()
    setNotifications((prev) => [...prev.slice(-2), { id, message, type }])
    window.setTimeout(() => dismiss(id), 4000)
  }, [dismiss])

  const value = useMemo(() => ({ notifications, notify, dismiss }), [notifications, notify, dismiss])

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}

export function useNotifications() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}
