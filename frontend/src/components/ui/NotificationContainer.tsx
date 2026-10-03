import { AnimatePresence, motion } from 'framer-motion'
import { useNotifications } from '../hooks/useNotifications'
import { X, AlertCircle, CheckCircle2 } from 'lucide-react'
import { createPortal } from 'react-dom'

export default function NotificationContainer() {
  const { notifications, dismiss } = useNotifications()

  return createPortal(
    <div className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 items-end">
      <AnimatePresence mode="popLayout">
        {notifications.map((n) => {
          const isError = n.type === 'error'
          return (
            <motion.div
              key={n.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, scale: 0.94 }}
              transition={{ type: 'spring', damping: 22, stiffness: 280 }}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium max-w-sm"
              style={{
                background: isError
                  ? 'rgba(248, 113, 113, 0.08)'
                  : 'var(--glass-strong)',
                border: isError
                  ? '1px solid rgba(248, 113, 113, 0.24)'
                  : '1px solid var(--border-strong)',
                color: isError ? 'var(--danger)' : 'var(--fg)',
                backdropFilter: 'blur(20px) saturate(1.3)',
                WebkitBackdropFilter: 'blur(20px) saturate(1.3)',
                boxShadow: 'var(--shadow-medium)',
              }}
            >
              {isError
                ? <AlertCircle className="w-4 h-4 flex-shrink-0 text-[var(--danger)]" />
                : <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-[var(--success)]" />
              }
              <span className="flex-1 leading-snug">{n.message}</span>
              <button
                onClick={() => dismiss(n.id)}
                className="p-0.5 rounded-md opacity-60 hover:opacity-100 transition-opacity"
                aria-label="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>,
    document.body
  )
}