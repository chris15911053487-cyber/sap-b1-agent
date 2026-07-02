import axios from 'axios'
import type {
  ChatRequest,
  ChatResponse,
  ConversationSummary,
  ConversationDetail,
  ConnectionTestRequest,
  ConnectionTestResponse,
  TableInfo,
  StreamCallbacks,
  VerifyResponse,
} from './types'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

export async function sendChatMessage(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/chat', req)
  return data
}

export async function listConversations(database?: string): Promise<ConversationSummary[]> {
  const { data } = await api.get<ConversationSummary[]>('/history', {
    params: database ? { database } : undefined,
  })
  return data
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const { data } = await api.get<ConversationDetail>(`/history/${id}`)
  return data
}

export async function deleteConversation(id: string): Promise<void> {
  await api.delete(`/history/${id}`)
}

export async function testConnection(req: ConnectionTestRequest): Promise<ConnectionTestResponse> {
  const { data } = await api.post<ConnectionTestResponse>('/connection/test', req)
  return data
}

export async function listTables(): Promise<TableInfo[]> {
  const { data } = await api.get<TableInfo[]>('/schema/tables')
  return data
}

export function streamChatMessage(
  req: ChatRequest,
  callbacks: StreamCallbacks,
): AbortController {
  const controller = new AbortController()

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: { message: 'Stream failed' } }))
      callbacks.onError?.({ error: err?.error?.message || err?.detail || '流式请求失败' })
      return
    }

    const reader = response.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let eventType = ''
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          dataStr = line.slice(6)
          _dispatchSSE(eventType, dataStr, callbacks)
          eventType = ''
          dataStr = ''
        }
      }
    }
  }).catch((err: Error) => {
    if (err.name !== 'AbortError') {
      callbacks.onError?.({ error: err.message || '网络错误' })
    }
  })

  return controller
}

function _dispatchSSE(eventType: string, dataStr: string, callbacks: StreamCallbacks): void {
  try {
    const data = JSON.parse(dataStr)
    switch (eventType) {
      case 'intent':
        callbacks.onIntent?.(data)
        break
      case 'sql':
        callbacks.onSql?.(data)
        break
      case 'data':
        callbacks.onData?.(data)
        break
      case 'explanation':
        callbacks.onExplanation?.(data)
        break
      case 'error':
        callbacks.onError?.(data)
        break
      case 'done':
        callbacks.onDone?.()
        break
    }
  } catch {
    // ignore parse errors for non-JSON data
  }
}

export async function runVerification(database: string): Promise<VerifyResponse> {
  const { data } = await api.post<VerifyResponse>('/verify', { database })
  return data
}
