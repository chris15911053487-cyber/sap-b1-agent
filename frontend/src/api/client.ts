import axios from 'axios'
import type {
  ChatRequest,
  ChatResponse,
  ConversationSummary,
  ConversationDetail,
  ConnectionTestRequest,
  ConnectionTestResponse,
  TableInfo,
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
