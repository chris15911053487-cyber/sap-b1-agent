import axios from 'axios'
import type {
  ChatRequest,
  ChatResponse,
  ConversationSummary,
  ConversationDetail,
  ConnectionTestRequest,
  ConnectionTestResponse,
  DatabaseInfo,
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

export async function listDatabases(): Promise<DatabaseInfo[]> {
  const { data } = await api.get<{ databases: DatabaseInfo[] }>('/connection/databases')
  return data.databases
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
    if (!reader) {
      callbacks.onError?.({ error: '浏览器不支持流式读取' })
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    // MUST be outside the while loop: a long data line (e.g. sp_arch 50KB+ JSON)
    // can span multiple TCP chunks. eventType set in one iteration must survive
    // into the next where the data line finally completes.
    let eventType = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
          if (eventType === 'sp_arch') console.log('[SSE] saw sp_arch event line')
        } else if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (eventType === 'sp_arch') console.log('[SSE] dispatching sp_arch, data length:', dataStr.length)
          _dispatchSSE(eventType, dataStr, callbacks)
          eventType = ''
        }
      }
    }
    callbacks.onDone?.()
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
      case 'sp_arch':
        callbacks.onSpArch?.(data)
        break
      case 'sp_deploy':
        callbacks.onSpDeploy?.(data)
        break
      case 'sp_verify':
        callbacks.onSpVerify?.(data)
        break
      case 'explanation':
        callbacks.onExplanation?.(data)
        break
      case 'error':
        callbacks.onError?.(data)
        break
      case 'progress':
        callbacks.onProgress?.(data)
        break
      case 'done':
        callbacks.onDone?.()
        break
    }
  } catch (e) {
    console.error(`[SSE] Failed to parse ${eventType} event:`, e, dataStr.slice(0, 200))
  }
}

export async function runVerification(database: string): Promise<VerifyResponse> {
  const { data } = await api.post<VerifyResponse>('/verify', { database })
  return data
}

/** 手动部署存储过程 */
export interface SpDeployInput {
  name: string
  generated_code: string
  dependencies: string[]
  parameters: Record<string, string>
}

export interface SpDeployRequest {
  procedures: SpDeployInput[]
  execution_order: string[]
  database?: string
}

export interface SpDeployResponse {
  deploy_total: number
  deploy_succeeded: number
  deploy_failed: number
  log_table_created: boolean
  deploy_results: Array<{
    name: string
    success: boolean
    action: string
    error: string
    execution_time_ms: number
  }>
  verify_total: number
  verify_passed: number
  verify_failed: number
  verify_results: Array<{
    name: string
    success: boolean
    error: string
    row_count: number
    execution_time_ms: number
    sample_output: string
  }>
}

export async function deployStoredProcedures(req: SpDeployRequest): Promise<SpDeployResponse> {
  const { data } = await api.post<SpDeployResponse>('/sp/deploy', req, { timeout: 120000 })
  return data
}
