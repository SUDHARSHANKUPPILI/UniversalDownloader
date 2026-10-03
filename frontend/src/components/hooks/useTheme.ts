import { useEffect, useState } from 'react'

type Theme = 'light' | 'dark' | 'system'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('ud-theme')
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'dark'
  })
  const [resolved, setResolved] = useState<'light' | 'dark'>('dark')

  useEffect(() => {
    localStorage.setItem('ud-theme', theme)
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const update = () => {
      const next = theme === 'system' ? (mq.matches ? 'light' : 'dark') : theme
      setResolved(next)
      document.documentElement.dataset.theme = next
      if (next === 'dark') {
        document.documentElement.classList.add('dark')
        document.documentElement.classList.remove('light')
      } else {
        document.documentElement.classList.add('light')
        document.documentElement.classList.remove('dark')
      }
    }
    update()
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [theme])

  return { theme, setTheme, resolved }
}
