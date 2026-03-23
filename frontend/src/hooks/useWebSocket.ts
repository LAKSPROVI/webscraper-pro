import { useEffect, useRef, useCallback, useState } from 'react'
import { useAppStore } from '../stores/appStore'

type WSEventType = 'job_created' | 'job_started' | 'job_progress' | 'job_done' | 'job_failed' | 'new_item' | 'system_status'

interface WSEvent {
  type: WSEventType
  data: unknown
}

type WSStatus = 'connected' | 'reconnecting' | 'disconnected' | 'error'

interface UseWebSocketReturn {
  status: WSStatus
  lastEvent: WSEvent | null
  subscribe: (eventType: WSEventType, callback: (data: unknown) => void) => () => void
}

function resolveWsBaseUrl(): string {
  const envWsUrl = import.meta.env.VITE_WS_URL as string | undefined
  if (envWsUrl) {
    return envWsUrl
  }

  if (typeof window === 'undefined') {
    return 'ws://localhost:8000'
  }

  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}`
}

const BASE_WS_URL = resolveWsBaseUrl()
const MAX_BACKOFF = 30000

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const backoffRef = useRef(1000)
  const mountedRef = useRef(true)
  const subscribersRef = useRef<Map<WSEventType, Set<(data: unknown) => void>>>(new Map())

  const [status, setStatus] = useState<WSStatus>('disconnected')
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null)

  const { updateJob, addRealtimeItem, setActiveJobsCount, setSystemStatus } = useAppStore()

  const handleEvent = useCallback((event: WSEvent) => {
    setLastEvent(event)

    switch (event.type) {
      case 'job_created':
      case 'job_started':
      case 'job_progress':
      case 'job_done':
      case 'job_failed': {
        const jobData = event.data as { id: string; [key: string]: unknown }
        if (jobData?.id) {
          updateJob(jobData.id, jobData as Parameters<typeof updateJob>[1])
        }
        break
      }
      case 'new_item': {
        const item = event.data as Parameters<typeof addRealtimeItem>[0]
        if (item) addRealtimeItem(item)
        break
      }
      case 'system_status': {
        const statusData = event.data as Parameters<typeof setSystemStatus>[0]
        if (statusData) setSystemStatus(statusData)
        break
      }
    }

    // Notifica subscribers
    const subs = subscribersRef.current.get(event.type)
    if (subs) {
      subs.forEach((cb) => cb(event.data))
    }
  }, [updateJob, addRealtimeItem, setSystemStatus])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(`${BASE_WS_URL}/api/v1/ws/jobs`)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setStatus('connected')
        backoffRef.current = 1000
        useAppStore.getState().setApiOnline(true)
      }

      ws.onmessage = (evt) => {
        try {
          const event: WSEvent = JSON.parse(evt.data)
          handleEvent(event)
        } catch {
          // mensagem inválida, ignorar
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setStatus('reconnecting')
        scheduleReconnect()
      }

      ws.onerror = () => {
        if (!mountedRef.current) return
        setStatus('error')
        ws.close()
      }
    } catch {
      setStatus('error')
      scheduleReconnect()
    }
  }, [handleEvent])

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)

    const delay = backoffRef.current
    backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF)

    reconnectTimeoutRef.current = setTimeout(() => {
      if (mountedRef.current) connect()
    }, delay)
  }, [connect])

  const subscribe = useCallback((eventType: WSEventType, callback: (data: unknown) => void) => {
    if (!subscribersRef.current.has(eventType)) {
      subscribersRef.current.set(eventType, new Set())
    }
    subscribersRef.current.get(eventType)!.add(callback)

    return () => {
      subscribersRef.current.get(eventType)?.delete(callback)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    // Heartbeat — verifica conexão a cada 30s
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      } else if (wsRef.current?.readyState === WebSocket.CLOSED) {
        connect()
      }
    }, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(heartbeat)
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  // Mock: simular dados em dev quando não há backend
  useEffect(() => {
    if (import.meta.env.DEV) {
      const mockInterval = setInterval(() => {
        const domains = ['news.ycombinator.com', 'reddit.com', 'github.com', 'medium.com', 'techcrunch.com']
        const spiders = ['generic', 'news', 'article']
        
        const mockItem = {
          id: crypto.randomUUID(),
          job_id: 'mock-job-1',
          url: `https://${domains[Math.floor(Math.random() * domains.length)]}/post/${Math.floor(Math.random() * 10000)}`,
          title: `Artigo de exemplo ${Math.floor(Math.random() * 1000)}`,
          content: 'Conteúdo coletado pelo spider automaticamente...',
          domain: domains[Math.floor(Math.random() * domains.length)],
          spider_type: spiders[Math.floor(Math.random() * spiders.length)],
          scraped_at: new Date().toISOString(),
        }
        addRealtimeItem(mockItem)
        setActiveJobsCount(Math.floor(Math.random() * 5) + 1)
      }, 3000)

      return () => clearInterval(mockInterval)
    }
  }, [addRealtimeItem, setActiveJobsCount])

  return { status, lastEvent, subscribe }
}
