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

export interface DatabaseInfo {
  name: string
  host: string
  port: number
  database: string
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

/** SSE 流式事件类型 */
export interface SSEIntentEvent {
  intent: string
  confidence: number
  conversation_id: string
}

export interface SSESqlEvent {
  sql: string
}

export interface SSEDataEvent {
  markdown?: string
  findings?: VerifyFindingItem[]
  pass_rate?: number
  total?: number
  passed?: number
  failed?: number
}

export interface SSEExplanationEvent {
  text: string
}

export interface SSEErrorEvent {
  error: string
}

export interface VerifyFindingItem {
  check_name: string
  status: string
  detail: string
}

/** 流式回调 */
export interface StreamCallbacks {
  onIntent?: (event: SSEIntentEvent) => void
  onSql?: (event: SSESqlEvent) => void
  onData?: (event: SSEDataEvent) => void
  onExplanation?: (event: SSEExplanationEvent) => void
  onError?: (event: SSEErrorEvent) => void
  onDone?: () => void
}

/** /api/verify 响应 */
export interface VerifyResponse {
  plan_name: string
  total_checks: number
  passed: number
  failed: number
  pass_rate: number
  findings: VerifyFindingItem[]
}
