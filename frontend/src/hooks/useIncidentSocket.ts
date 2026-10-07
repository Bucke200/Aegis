import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { ensureAccessToken, getAccessToken, setAccessToken, websocketUrl } from '../api/client'
import type { SocketEvent } from '../api/types'

export function useIncidentSocket(enabled: boolean) {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | null>(null)
  const debounceRef = useRef<number | null>(null)
  const attemptsRef = useRef(0)

  useEffect(() => {
    if (!enabled) {
      return
    }
    let cancelled = false

    const invalidate = (event?: SocketEvent) => {
      void queryClient.invalidateQueries({ queryKey: ['incidents'] })
      if (event?.incident_id) {
        void queryClient.invalidateQueries({ queryKey: ['incident', event.incident_id] })
      }
    }

    const scheduleInvalidate = (event?: SocketEvent) => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current)
      }
      debounceRef.current = window.setTimeout(() => invalidate(event), 400)
    }

    const connect = async () => {
      if (cancelled) {
        return
      }
      const token = getAccessToken() ?? (await ensureAccessToken())
      if (!token || cancelled) {
        return
      }
      const socket = new WebSocket(`${websocketUrl()}?token=${encodeURIComponent(token)}`)
      socketRef.current = socket

      socket.onopen = () => {
        attemptsRef.current = 0
        setConnected(true)
        scheduleInvalidate()
      }
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as SocketEvent
          if (event.type !== 'ready') {
            scheduleInvalidate(event)
          }
        } catch {
          // Ignore malformed frames; the gateway only sends JSON.
        }
      }
      socket.onerror = () => {
        socket.close()
      }
      socket.onclose = (event) => {
        setConnected(false)
        socketRef.current = null
        if (cancelled) {
          return
        }
        if (event.code === 1008) {
          setAccessToken(null)
        }
        const delay = Math.min(1000 * 2 ** attemptsRef.current, 30_000)
        attemptsRef.current += 1
        timerRef.current = window.setTimeout(() => {
          void connect()
        }, delay)
      }
    }

    void connect()

    return () => {
      cancelled = true
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
      }
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current)
      }
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [enabled, queryClient])

  return { connected }
}
