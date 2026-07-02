/** 后端 API 响应类型 */

export interface ChatRequest {
  message: string
  database?: string
  conversation_id?: string | null
}

export interface ChatResponse {
  intent: string
  sql: string
  data: { markdown: string } | null
  explanation: string
  conversation_id: string
  success: boolean
  error: string
}

export interface ConversationSummary {
  id: string
  title: string
  database: string
  created_at: string
  message_count: number
}

export interface MessageDetail {
  id: string
  role: 'user' | 'assistant'
  content: string
  intent: string
  sql: string
  data_json: string
  created_at: string
}

export interface ConversationDetail {
  id: string
  title: string
  database: string
  created_at: string
  messages: MessageDetail[]
}

export interface ConnectionTestRequest {
  database?: string
}

export interface ConnectionTestResponse {
  success: boolean
  message: string
  database: string
  host: string
  port: number
}

export interface TableInfo {
  name: string
  description: string
  column_count: number
  columns: ColumnInfo[]
}

export interface ColumnInfo {
  name: string
  data_type: string
  is_nullable: boolean
  is_primary_key: boolean
  description: string
}
