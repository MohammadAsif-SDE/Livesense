import { useEffect, useRef } from 'react'
import type { SpeakerEvent } from '../types'
import { useLiveStore } from '../store/liveStore'

// Use wss:// when the page is served over HTTPS (e.g. Vite dev server with basicSsl)
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
const RECONNECT_DELAY_MS = 3000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { setConnected, ingestEvent } = useLiveStore()

  useEffect(() => {
    let unmounted = false

    function connect() {
      if (unmounted) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      }

      ws.onmessage = (msg: MessageEvent<string>) => {
        try {
          const event: SpeakerEvent = JSON.parse(msg.data)
          if (event.event_type === 'speaker_event') {
            ingestEvent(event)
          }
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // Only auto-reconnect if this wasn't triggered by intentional cleanup
        // (e.g. React StrictMode double-mount in dev)
        if (!unmounted) {
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      unmounted = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [setConnected, ingestEvent])

  return wsRef
}
