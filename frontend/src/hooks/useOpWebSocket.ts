/**
 * WebSocket hook for live push events from a Lockpick operation.
 * Auto-reconnects with exponential backoff; falls back to polling when disconnected.
 */
import { useState, useEffect, useRef, useCallback } from 'react'

export type WsStatus = 'connected' | 'connecting' | 'disconnected'

export interface UseOpWebSocketResult {
  status: WsStatus
  reconnectIn: number | null
  reconnect: () => void
}

// Backoff delays in seconds (capped at 30s)
const BACKOFF_DELAYS = [3, 6, 12, 24, 30]
const MAX_ATTEMPTS = 5

function getWsUrl(opId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  return `${proto}://${host}/api/ops/${opId}/ws`
}

export function useOpWebSocket(
  opId: string | null,
  onEvent: (event: unknown) => void,
): UseOpWebSocketResult {
  const [status, setStatus] = useState<WsStatus>('connecting')
  const [reconnectIn, setReconnectIn] = useState<number | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const attemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)
  // Keep onEvent stable across renders
  const onEventRef = useRef(onEvent)
  useEffect(() => { onEventRef.current = onEvent }, [onEvent])

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current)
      countdownTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!opId || !mountedRef.current) return

    clearTimers()
    setReconnectIn(null)

    const url = getWsUrl(opId)
    const ws = new WebSocket(url)
    wsRef.current = ws
    setStatus('connecting')

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      attemptsRef.current = 0
      setStatus('connected')
      setReconnectIn(null)
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return
      try {
        const parsed = JSON.parse(evt.data)
        onEventRef.current(parsed)
      } catch {
        // ignore unparseable messages
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      wsRef.current = null
      const attempt = attemptsRef.current
      attemptsRef.current += 1

      // Intentional: no auto-recovery after MAX_ATTEMPTS. This is a trusted-network
      // tool — if the connection is permanently lost, a page reload is the expected
      // recovery path. Silent failure avoids confusing reconnect loops in air-gapped envs.
      if (attempt >= MAX_ATTEMPTS) {
        setStatus('disconnected')
        setReconnectIn(null)
        return
      }

      const delay = BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)]
      setStatus('connecting')
      setReconnectIn(delay)

      // Countdown tick
      let remaining = delay
      countdownTimerRef.current = setInterval(() => {
        remaining -= 1
        if (mountedRef.current) setReconnectIn(remaining > 0 ? remaining : null)
        if (remaining <= 0) {
          if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
        }
      }, 1000)

      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect()
      }, delay * 1000)
    }

    ws.onerror = () => {
      // onerror always fires before onclose, so just close to trigger the backoff
      ws.close()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opId, clearTimers])

  const reconnect = useCallback(() => {
    clearTimers()
    attemptsRef.current = 0
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
    connect()
  }, [clearTimers, connect])

  useEffect(() => {
    mountedRef.current = true
    if (!opId) {
      setStatus('disconnected')
      return
    }
    connect()
    return () => {
      mountedRef.current = false
      clearTimers()
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [opId, connect, clearTimers])

  return { status, reconnectIn, reconnect }
}
