/**
 * Browser Desktop Notification Utilities
 */

export type NotificationPermissionState = 'Not requested' | 'Granted' | 'Denied' | 'Unsupported'

export function isNotificationSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function getNotificationPermissionState(): NotificationPermissionState {
  if (!isNotificationSupported()) {
    return 'Unsupported'
  }
  switch (Notification.permission) {
    case 'granted':
      return 'Granted'
    case 'denied':
      return 'Denied'
    default:
      return 'Not requested'
  }
}

export async function requestNotificationPermission(): Promise<NotificationPermissionState> {
  if (!isNotificationSupported()) {
    return 'Unsupported'
  }
  try {
    const result = await Notification.requestPermission()
    if (result === 'granted') return 'Granted'
    if (result === 'denied') return 'Denied'
    return 'Not requested'
  } catch {
    return getNotificationPermissionState()
  }
}

export function sendDesktopNotification(title: string, options?: NotificationOptions): boolean {
  if (!isNotificationSupported()) return false
  if (Notification.permission !== 'granted') return false
  try {
    new Notification(title, options)
    return true
  } catch (e) {
    // Gracefully ignore constructor errors in non-standard environments
    console.warn('Failed to display desktop notification:', e)
    return false
  }
}
