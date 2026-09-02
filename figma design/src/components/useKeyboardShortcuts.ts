import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '../lib/queryProvider'

function isTypingTarget(target: EventTarget | null) {
  const element = target as HTMLElement | null
  return element?.isContentEditable || element?.tagName === 'INPUT' || element?.tagName === 'TEXTAREA' || element?.tagName === 'SELECT'
}

function focusSearch() {
  const search = document.querySelector<HTMLElement>('input[type="search"], input[aria-label*="search" i], input[placeholder*="search" i]')
  search?.focus()
}

export function useKeyboardShortcuts(onNotifications: () => void) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  useEffect(() => {
    let navigationPrefix = false
    let prefixTimer: number | undefined

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return

      if (navigationPrefix) {
        navigationPrefix = false
        if (prefixTimer) window.clearTimeout(prefixTimer)
        const destinations: Record<string, string> = { d: '/', t: '/topology', a: '/alerts', s: '/snmp/devices', f: '/flow-analytics' }
        const destination = destinations[event.key.toLowerCase()]
        if (destination) {
          event.preventDefault()
          navigate(destination)
        }
        return
      }

      if (event.key === 'g') {
        navigationPrefix = true
        prefixTimer = window.setTimeout(() => { navigationPrefix = false }, 1000)
        return
      }
      if (event.key === '/') {
        event.preventDefault()
        focusSearch()
      } else if (event.key.toLowerCase() === 'r') {
        event.preventDefault()
        void queryClient.invalidateQueries()
      } else if (event.key.toLowerCase() === 'n') {
        event.preventDefault()
        onNotifications()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      if (prefixTimer) window.clearTimeout(prefixTimer)
    }
  }, [navigate, onNotifications, queryClient])
}
