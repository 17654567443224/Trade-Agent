import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'
import type { WsEvent } from '../types'

// 直连后端 8000 端口，绕过 Vite 代理
const WS_URL = `ws://127.0.0.1:8000/ws`
const RECONNECT_DELAY = 3000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const {
    setConnected,
    setSystemStatus,
    setSymbols,
    setKlines,
    updateKlineBar,
    setPositions,
    setOrders,
    setAnalystReport,
    setDecision,
    addSignal,
    addReflection,
    applySnapshot,
    startQuery,
    updateQueryAnalyst,
    appendQueryToken,
    finishQuery,
    errorQuery,
  } = useStore()

  const connect = () => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onclose = () => {
      setConnected(false)
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (ev) => {
      try {
        const event: WsEvent = JSON.parse(ev.data)
        switch (event.type) {
          case 'snapshot':
            applySnapshot(event.data)
            break
          case 'signal':
            addSignal(event.data)
            break
          case 'state':
            setPositions(event.data.positions)
            setOrders(event.data.orders)
            if (event.data.symbols?.length) setSymbols(event.data.symbols)
            break
          case 'analyst':
            setAnalystReport(event.data)
            break
          case 'decision':
            setDecision(event.data)
            break
          case 'kline': {
            const key = `${event.data.exchange}:${event.data.instId}`
            setKlines(key, event.data)
            break
          }
          case 'kline_bar': {
            const key = `${event.data.exchange}:${event.data.instId}`
            updateKlineBar(key, event.data.bar)
            break
          }
          case 'reflection':
            addReflection(event.data)
            break
          case 'system':
            setSystemStatus(event.data.status)
            break
          case 'query_status':
            if (event.data.status === 'started') {
              startQuery({
                query_id: event.data.query_id,
                question: '',   // filled by QueryPanel optimistically
                instId: event.data.instId ?? '',
                analystStatus: { chart: 'pending', fundamental: 'pending', risk: 'pending' },
                reports: {},
                streamingContent: '',
                finalContent: '',
                status: 'running',
                timestamp: Date.now(),
              })
            }
            break
          case 'query_analyst': {
            const { query_id, role, status, content } = event.data
            updateQueryAnalyst(query_id, role, status as any, content)
            break
          }
          case 'query_token':
            appendQueryToken(event.data.query_id, event.data.token)
            break
          case 'query_done':
            finishQuery(event.data.query_id, event.data.content)
            break
          case 'query_error':
            errorQuery(event.data.query_id, event.data.error)
            break
        }
      } catch {
        // ignore malformed messages
      }
    }
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // allow manual ping to keep alive
  const ping = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send('ping')
    }
  }

  useEffect(() => {
    const id = setInterval(ping, 20_000)
    return () => clearInterval(id)
  }, [])
}
