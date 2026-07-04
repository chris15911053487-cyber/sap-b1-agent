import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sendChatMessage, streamChatMessage, listConversations, getConversation, deleteConversation } from '../api/client'
import type { ConversationSummary, MessageDetail, ChatResponse, SSEIntentEvent, SSESqlEvent, SSEDataEvent, SSEExplanationEvent, SSEErrorEvent, SSESpArchEvent, SSEProgressEvent } from '../api/types'

/** Generate a UUID v4 — works in both secure and insecure contexts. */
function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback for non-secure contexts (HTTP)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  intent: string
  sql: string
  dataMarkdown: string
  spArchData?: SSESpArchEvent
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
      id: generateUUID(),
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
        id: generateUUID(),
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
      id: generateUUID(),
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
    const assistantId = generateUUID()
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

    // Timeout watchdog: if no event arrives within 20s, show error and stop loading
    let streamTimeout: ReturnType<typeof setTimeout> | null = setTimeout(() => {
      if (isLoading.value) {
        updateAssistant(assistantId, {
          content: '请求超时 — 后端可能正在处理长时间任务，请检查服务器日志或重试。',
        })
        error.value = '流式响应超时（20s），请重试'
        isLoading.value = false
        _abortController?.abort()
        _abortController = null
      }
    }, 20000)

    function resetTimeout() {
      if (streamTimeout) {
        clearTimeout(streamTimeout)
        streamTimeout = setTimeout(() => {
          if (isLoading.value) {
            updateAssistant(assistantId, {
              content: '处理时间较长，请耐心等待或检查服务器状态。',
            })
          }
        }, 60000) // After first event, give 60s instead of 20s
      }
    }

    _abortController = streamChatMessage(
      { message: content, database, conversation_id: activeConversationId.value },
      {
        onIntent: (event: SSEIntentEvent) => {
          resetTimeout()
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
          resetTimeout()
          updateAssistant(assistantId, {
            sql: event.sql,
            content: `正在执行 SQL...`,
          })
        },
        onData: (event: SSEDataEvent) => {
          resetTimeout()
          const md = event.markdown || ''
          updateAssistant(assistantId, {
            dataMarkdown: md,
            content: md ? '查询结果已返回' : '处理中...',
          })
        },
        onSpArch: (event: SSESpArchEvent) => {
          resetTimeout()
          console.log('[onSpArch] received:', event.name, 'procedures:', event.procedures?.length)
          updateAssistant(assistantId, {
            spArchData: event,
            intent: 'build_sp',
            content: `存储过程体系: ${event.name}`,
          })
        },
        onExplanation: (event: SSEExplanationEvent) => {
          resetTimeout()
          updateAssistant(assistantId, {
            explanation: event.text,
            content: event.text,
          })
        },
        onProgress: (event: SSEProgressEvent) => {
          resetTimeout()
          updateAssistant(assistantId, {
            content: event.message,
          })
        },
        onError: (event: SSEErrorEvent) => {
          if (streamTimeout) { clearTimeout(streamTimeout); streamTimeout = null }
          updateAssistant(assistantId, {
            content: event.error,
          })
          error.value = event.error
          isLoading.value = false
        },
        onDone: () => {
          if (streamTimeout) { clearTimeout(streamTimeout); streamTimeout = null }
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
    let spArchData: SSESpArchEvent | undefined
    try {
      if (m.data_json) {
        const parsed = JSON.parse(m.data_json)
        // Check if this is SP architecture data (has name + procedures)
        if (parsed.name && parsed.procedures) {
          spArchData = parsed as SSESpArchEvent
        } else {
          dataMarkdown = parsed.markdown || ''
        }
      }
    } catch { /* ignore parse errors */ }

    return {
      id: m.id,
      role: m.role,
      content: m.content,
      intent: m.intent,
      sql: m.sql,
      dataMarkdown,
      spArchData,
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
