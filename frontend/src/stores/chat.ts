import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sendChatMessage, streamChatMessage, listConversations, getConversation, deleteConversation } from '../api/client'
import type { ConversationSummary, MessageDetail, ChatResponse, SSEIntentEvent, SSESqlEvent, SSEDataEvent, SSEExplanationEvent, SSEErrorEvent } from '../api/types'

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  intent: string
  sql: string
  dataMarkdown: string
  explanation: string
  timestamp: Date
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<DisplayMessage[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  let _abortController: AbortController | null = null

  const activeConversation = computed(() =>
    conversations.value.find(c => c.id === activeConversationId.value) || null
  )

  async function fetchConversations(database?: string) {
    conversations.value = await listConversations(database)
  }

  async function selectConversation(id: string) {
    activeConversationId.value = id
    try {
      const detail = await getConversation(id)
      messages.value = detail.messages.map(m => toDisplayMessage(m))
    } catch {
      error.value = '加载对话失败'
    }
  }

  async function sendMessage(content: string, database: string) {
    // Add user message immediately
    const userMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      intent: '',
      sql: '',
      dataMarkdown: '',
      explanation: '',
      timestamp: new Date(),
    }
    messages.value.push(userMsg)
    isLoading.value = true
    error.value = null

    try {
      const response: ChatResponse = await sendChatMessage({
        message: content,
        database,
        conversation_id: activeConversationId.value,
      })

      // Update active conversation ID if this was a new conversation
      if (!activeConversationId.value) {
        activeConversationId.value = response.conversation_id
        await fetchConversations(database)
      }

      // Add assistant message
      const assistantMsg: DisplayMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.explanation,
        intent: response.intent,
        sql: response.sql,
        dataMarkdown: response.data?.markdown || '',
        explanation: response.explanation,
        timestamp: new Date(),
      }
      messages.value.push(assistantMsg)
    } catch (e: any) {
      error.value = e?.message || '发送失败'
    } finally {
      isLoading.value = false
    }
  }

  async function removeConversation(id: string) {
    await deleteConversation(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeConversationId.value === id) {
      activeConversationId.value = null
      messages.value = []
    }
  }

  function newConversation() {
    activeConversationId.value = null
    messages.value = []
    error.value = null
  }

  async function sendMessageStream(content: string, database: string) {
    // Abort any previous stream
    if (_abortController) {
      _abortController.abort()
    }

    // Add user message immediately
    const userMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      intent: '',
      sql: '',
      dataMarkdown: '',
      explanation: '',
      timestamp: new Date(),
    }
    messages.value.push(userMsg)
    isLoading.value = true
    error.value = null

    // Create placeholder assistant message
    const assistantId = crypto.randomUUID()
    const assistantMsg: DisplayMessage = {
      id: assistantId,
      role: 'assistant',
      content: '思考中...',
      intent: '',
      sql: '',
      dataMarkdown: '',
      explanation: '',
      timestamp: new Date(),
    }
    messages.value.push(assistantMsg)

    _abortController = streamChatMessage(
      { message: content, database, conversation_id: activeConversationId.value },
      {
        onIntent: (event: SSEIntentEvent) => {
          updateAssistant(assistantId, {
            intent: event.intent,
            content: `识别意图: ${event.intent}`,
          })
          if (!activeConversationId.value) {
            activeConversationId.value = event.conversation_id
            fetchConversations(database)
          }
        },
        onSql: (event: SSESqlEvent) => {
          updateAssistant(assistantId, {
            sql: event.sql,
            content: `正在执行 SQL...`,
          })
        },
        onData: (event: SSEDataEvent) => {
          const md = event.markdown || ''
          updateAssistant(assistantId, {
            dataMarkdown: md,
            content: md ? '查询结果已返回' : '处理中...',
          })
        },
        onExplanation: (event: SSEExplanationEvent) => {
          updateAssistant(assistantId, {
            explanation: event.text,
            content: event.text,
          })
        },
        onError: (event: SSEErrorEvent) => {
          updateAssistant(assistantId, {
            content: event.error,
          })
          error.value = event.error
        },
        onDone: () => {
          isLoading.value = false
          _abortController = null
        },
      },
    )
  }

  function updateAssistant(id: string, updates: Partial<DisplayMessage>) {
    const idx = messages.value.findIndex(m => m.id === id)
    if (idx !== -1) {
      messages.value[idx] = { ...messages.value[idx], ...updates }
    }
  }

  function toDisplayMessage(m: MessageDetail): DisplayMessage {
    let dataMarkdown = ''
    try {
      if (m.data_json) {
        const parsed = JSON.parse(m.data_json)
        dataMarkdown = parsed.markdown || ''
      }
    } catch { /* ignore parse errors */ }

    return {
      id: m.id,
      role: m.role,
      content: m.content,
      intent: m.intent,
      sql: m.sql,
      dataMarkdown,
      explanation: m.content,
      timestamp: new Date(m.created_at),
    }
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    messages,
    isLoading,
    error,
    fetchConversations,
    selectConversation,
    sendMessage,
    removeConversation,
    newConversation,
    sendMessageStream,
  }
})
