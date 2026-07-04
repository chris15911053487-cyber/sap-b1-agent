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

/** SSE progress 事件 — 长时间操作的状态更新 */
export interface SSEProgressEvent {
  stage: string
  message: string
}

export interface VerifyFindingItem {
  check_name: string
  status: string
  detail: string
}

/** SP 架构 — 单个存储过程 */
export interface SpArchProcedure {
  name: string
  description: string
  dependencies: string[]
  output_table: string
  parameters: Record<string, string>
  business_logic: string
  generated_code: string
  verification_checks?: VerificationCheckDef[]
}

/** 业务对账断言定义 */
export interface VerificationCheckDef {
  name: string
  description: string
  category: string
  check_sql: string
  assertion: string
  severity: string
}

/** 单条断言的验证结果 */
export interface CheckResultItem {
  name: string
  description: string
  category: string
  severity: string
  passed: boolean
  assertion: string
  actual_values: Record<string, any>
  detail: string
  check_sql: string
}

/** 一个 SP 的业务对账验证报告 */
export interface ValidationReportItem {
  sp_name: string
  total: number
  passed: number
  failed: number
  has_error_failures: boolean
  results: CheckResultItem[]
}

/** POST /api/sp/validate 响应 */
export interface SpValidateResponse {
  reports: ValidationReportItem[]
  total_checks: number
  total_passed: number
  total_failed: number
  has_error_failures: boolean
}

/** 修复循环单次迭代 */
export interface SpRepairIteration {
  iteration: number
  generated_code: string
  deploy_success: boolean
  deploy_error: string
  validation_report: ValidationReportItem | Record<string, never>
  passed: boolean
  llm_error: string
}

/** POST /api/sp/repair 响应 */
export interface SpRepairResponse {
  sp_name: string
  success: boolean
  message: string
  iterations: SpRepairIteration[]
  final_code: string
  final_report: ValidationReportItem | Record<string, never>
}

/** SSE sp_arch 事件 */
export interface SSESpArchEvent {
  name: string
  description: string
  design_notes: string
  procedures: SpArchProcedure[]
  execution_order: string[]
}

/** SP 部署 — 单个结果 */
export interface SpDeployResultItem {
  name: string
  success: boolean
  action: string  // "created" | "replaced" | "skipped" | "failed"
  error: string
  execution_time_ms: number
}

/** SSE sp_deploy 事件 */
export interface SSESpDeployEvent {
  total: number
  succeeded: number
  failed: number
  log_table_created: boolean
  results: SpDeployResultItem[]
}

/** SP 验证 — 单个结果 */
export interface SpVerifyResultItem {
  name: string
  success: boolean
  error: string
  row_count: number
  execution_time_ms: number
  sample_output: string
}

/** SSE sp_verify 事件 */
export interface SSESpVerifyEvent {
  total: number
  passed: number
  failed: number
  results: SpVerifyResultItem[]
}

/** SSE message_id 事件 — 后端持久化后返回真实的消息 ID */
export interface SSEMessageIdEvent {
  message_id: string
}

/** 流式回调 */
export interface StreamCallbacks {
  onIntent?: (event: SSEIntentEvent) => void
  onSql?: (event: SSESqlEvent) => void
  onData?: (event: SSEDataEvent) => void
  onSpArch?: (event: SSESpArchEvent) => void
  onSpDeploy?: (event: SSESpDeployEvent) => void
  onSpVerify?: (event: SSESpVerifyEvent) => void
  onExplanation?: (event: SSEExplanationEvent) => void
  onError?: (event: SSEErrorEvent) => void
  onProgress?: (event: SSEProgressEvent) => void
  onMessageId?: (event: SSEMessageIdEvent) => void
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
