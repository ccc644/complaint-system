// 0724 WebSocket 实时推送 — 自动重连 + 事件分发
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { useComplaintsStore } from '@/stores/complaints'
import { useNotificationsStore } from '@/stores/notifications'

// 0727 改用 sessionStorage：每个标签页独立存储 token，多角色同时登录互不干扰
const wsStorage = sessionStorage

type WsEvent = {
  type: 'complaint_created' | 'complaint_updated' | 'complaint_deleted' | 'ping'
  complaint_id: number
  complaint_no: string
  status: string
  message: string
}

type EventHandler = (event: WsEvent) => void

const handlers = new Set<EventHandler>()

export function onWsEvent(fn: EventHandler) {
  handlers.add(fn)
  return () => handlers.delete(fn)
}

/** 全局 WebSocket 状态（单例） */
const wsConnected = ref(false)
const wsReconnecting = ref(false)

export function useWebSocket() {
  const toast = useToast()
  const complaintsStore = useComplaintsStore()

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let reconnectAttempts = 0
  let destroyed = false

  function getWsUrl(): string {
    // 0727 生产部署：同源时从 window.location 自动推导 WS URL，无需配置
    if (import.meta.env.PROD) {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = wsStorage.getItem('token') || ''
      return `${proto}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`
    }
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8506'
    const wsBase = apiBase.replace(/^http/, 'ws')
    const token = wsStorage.getItem('token') || ''
    return `${wsBase}/api/ws?token=${encodeURIComponent(token)}`
  }

  function clearTimers() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
  }

  async function handleEvent(event: WsEvent) {
    // 自动刷新工单列表
    if (event.type === 'complaint_created' || event.type === 'complaint_updated') {
      try {
        await complaintsStore.fetchList()
      } catch { /* 静默失败 */ }
    } else if (event.type === 'complaint_deleted') {
      try {
        // 如果当前在详情页看到被删除的工单，刷新列表
        await complaintsStore.fetchList()
      } catch { /* 静默失败 */ }
    }

    // 通知 toast
    if (event.type !== 'ping') {
      const iconMap: Record<string, string> = {
        complaint_created: '📝',
        complaint_updated: '🔄',
        complaint_deleted: '🗑️',
      }
      const icon = iconMap[event.type] || '📌'
      toast.info(`${icon} ${event.message || `${event.complaint_no} ${event.status}`}`)
    }

    // 0729 WebSocket 事件后刷新通知未读数
    try {
      const notifStore = useNotificationsStore()
      await notifStore.refreshCount()
    } catch { /* 静默 */ }

    // 分发到自定义处理器
    handlers.forEach(fn => {
      try { fn(event) } catch { /* ignore */ }
    })
  }

  function connect() {
    if (destroyed) return
    clearTimers()

    const wsUrl = getWsUrl()
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      reconnectAttempts = 0
      wsConnected.value = true
      wsReconnecting.value = false
      // 心跳：每 25 秒发一次 ping（服务端 30s 超时）
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 25_000)
    }

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as WsEvent
        // 忽略服务端心跳响应
        if (event.type === 'ping' || msg.data === 'pong') return
        handleEvent(event)
      } catch { /* 忽略解析失败的消息 */ }
    }

    ws.onclose = () => {
      wsConnected.value = false
      clearTimers()
      if (!destroyed) {
        scheduleReconnect()
      }
    }

    ws.onerror = () => {
      // onclose 会在 onerror 之后触发，由 onclose 负责重连
    }
  }

  function scheduleReconnect() {
    if (destroyed) return
    // 指数退避：1s → 2s → 4s → 8s → 16s → 最大 30s
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30_000)
    reconnectAttempts++
    wsReconnecting.value = true
    reconnectTimer = setTimeout(() => connect(), delay)
  }

  function disconnect() {
    destroyed = true
    clearTimers()
    wsConnected.value = false
    wsReconnecting.value = false
    if (ws) {
      ws.onclose = null // 防止触发重连
      ws.close()
      ws = null
    }
  }

  onMounted(() => {
    const token = wsStorage.getItem('token')
    if (token) {
      connect()
    }
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected: wsConnected,
    reconnecting: wsReconnecting,
    disconnect,
    reconnect: connect,
  }
}
