# Vue 3 前端 — 二期实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 Vue 3 + Naive UI 前端，实现对话页面（左侧对话列表 + 聊天区域 + 输入框），对接已有后端 API。

**Architecture:** Vite 开发服务器代理 `/api/*` 到 `localhost:8000`。Pinia 管理对话和设置状态。Vue Router 三页面路由。组件自底向上构建：原子组件 → 复合组件 → 页面。

**Tech Stack:** Vue 3 (Composition API), TypeScript, Vite, Naive UI, Pinia, Vue Router, axios, highlight.js, marked

## Global Constraints

- **Node.js >= 18** (Vite 5 要求)
- 所有前端文件在 `frontend/` 目录下，不修改 `backend/`、`agent/` 等
- 组件命名 PascalCase，文件命名 PascalCase.vue
- TypeScript 严格模式
- API 代理：Vite `server.proxy` 将 `/api` 转发到 `http://localhost:8000`
- 使用 Naive UI 组件库，不引入其他 UI 库
- 对话页面为主要界面，校验页和设置页为占位符
- 非流式请求（SSE 流式留到三期）

---

### Task 1: Scaffold Vite + Vue 3 + TypeScript project

**Files:**
- Create: `frontend/` (entire Vite project scaffold)

- [ ] **Step 1: Create Vite project**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent
npm create vite@latest frontend -- --template vue-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install
npm install naive-ui vue-router@4 pinia axios highlight.js marked
npm install -D @types/marked
```

- [ ] **Step 3: Verify scaffold works**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: no type errors (may have unused variable warnings from scaffold — acceptable)

- [ ] **Step 4: Commit**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/ frontend/public/
git commit -m "feat(frontend): scaffold Vite + Vue 3 + TypeScript project"
```

### Task 2: Configure Vite, Router, Axios, and project structure

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Clean up: remove scaffold boilerplate files

- [ ] **Step 1: Write `frontend/src/api/types.ts`**

```typescript
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
```

- [ ] **Step 2: Write `frontend/src/api/client.ts`**

```typescript
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
```

- [ ] **Step 3: Write `frontend/src/router/index.ts`**

```typescript
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
    },
    {
      path: '/verify',
      name: 'verify',
      component: () => import('../views/VerifyView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

export default router
```

- [ ] **Step 4: Configure `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 5: Clean up scaffold boilerplate**

Remove `frontend/src/components/HelloWorld.vue`, `frontend/src/assets/vue.svg`, `frontend/public/vite.svg`. Clear `frontend/src/style.css`.

- [ ] **Step 6: Verify — TypeScript check passes**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: no type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/vite.config.ts frontend/src/router/ frontend/src/api/ frontend/src/style.css
git rm frontend/src/components/HelloWorld.vue frontend/src/assets/vue.svg frontend/public/vite.svg 2>/dev/null
git commit -m "feat(frontend): configure Vite proxy, Vue Router, Axios client, API types"
```

### Task 3: Pinia stores — chat and settings

**Files:**
- Create: `frontend/src/stores/chat.ts`
- Create: `frontend/src/stores/settings.ts`

**Interfaces:**
- Produces: `useChatStore` (Pinia store), `useSettingsStore` (Pinia store)
- Consumes: `api/client.ts` functions from Task 2, `types.ts` from Task 2

- [ ] **Step 1: Write `frontend/src/stores/settings.ts`**

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  const activeDatabase = ref<string>('test')
  const sidebarCollapsed = ref(false)

  function setDatabase(db: string) {
    activeDatabase.value = db
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { activeDatabase, sidebarCollapsed, setDatabase, toggleSidebar }
})
```

- [ ] **Step 2: Write `frontend/src/stores/chat.ts`**

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sendChatMessage, listConversations, getConversation, deleteConversation } from '../api/client'
import type { ConversationSummary, MessageDetail, ChatResponse } from '../api/types'

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
  }
})
```

- [ ] **Step 3: Verify TypeScript check**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/
git commit -m "feat(frontend): add Pinia stores for chat and settings"
```

### Task 4: Leaf components — IntentBadge, SqlBlock, DataTable, Explanation

**Files:**
- Create: `frontend/src/components/IntentBadge.vue`
- Create: `frontend/src/components/SqlBlock.vue`
- Create: `frontend/src/components/DataTable.vue`
- Create: `frontend/src/components/Explanation.vue`

**Interfaces:**
- `IntentBadge` — Props: `intent: string`
- `SqlBlock` — Props: `sql: string`
- `DataTable` — Props: `markdown: string`
- `Explanation` — Props: `text: string`

- [ ] **Step 1: Write `frontend/src/components/IntentBadge.vue`**

```vue
<script setup lang="ts">
defineProps<{ intent: string }>()

const intentLabels: Record<string, string> = {
  query: '查询',
  build_sp: '构建SP',
  verify: '校验',
  chat: '对话',
}

const intentColors: Record<string, string> = {
  query: '#2080f0',
  build_sp: '#f0a020',
  verify: '#18a058',
  chat: '#909399',
}
</script>

<template>
  <n-tag
    :color="{ color: intentColors[intent] || '#909399', textColor: '#fff' }"
    size="small"
    round
  >
    {{ intentLabels[intent] || intent }}
  </n-tag>
</template>
```

- [ ] **Step 2: Write `frontend/src/components/SqlBlock.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('sql', sql)

const props = defineProps<{ sql: string }>()

const highlighted = hljs.highlight(props.sql, { language: 'sql' }).value

const copied = ref(false)
function copySql() {
  navigator.clipboard.writeText(props.sql)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}
</script>

<template>
  <div class="sql-block">
    <div class="sql-header">
      <span class="sql-label">SQL</span>
      <n-button size="tiny" text @click="copySql">
        {{ copied ? '已复制' : '复制' }}
      </n-button>
    </div>
    <pre><code class="language-sql" v-html="highlighted"></code></pre>
  </div>
</template>

<style scoped>
.sql-block {
  background: #f6f8fa;
  border-radius: 6px;
  overflow: hidden;
  margin: 8px 0;
}
.sql-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #e8eaed;
  font-size: 12px;
}
.sql-label {
  font-weight: 600;
  color: #666;
}
pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
}
</style>
```

- [ ] **Step 3: Write `frontend/src/components/DataTable.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ markdown: string }>()

// Parse simple markdown table into structured data
const tableData = computed(() => {
  if (!props.markdown) return null
  const lines = props.markdown.trim().split('\n')
  if (lines.length < 2) return null

  // Parse header
  const headers = lines[0]
    .split('|')
    .map(h => h.trim())
    .filter(Boolean)

  // Skip separator line (line[1])
  // Parse data rows (skip last line if it starts with _)
  const rows = lines.slice(2)
    .filter(line => !line.startsWith('_'))
    .map(line =>
      line
        .split('|')
        .map(c => c.trim())
        .filter(Boolean)
    )

  return { headers, rows }
})
</script>

<template>
  <div v-if="tableData" class="data-table">
    <n-data-table
      :columns="tableData.headers.map((h, i) => ({ title: h, key: String(i) }))"
      :data="tableData.rows.map((row, ri) => {
        const obj: Record<string, string> = { key: String(ri) }
        row.forEach((cell, ci) => { obj[String(ci)] = cell })
        return obj
      })"
      :max-height="400"
      :single-line="false"
      size="small"
      striped
    />
  </div>
  <div v-else-if="markdown" class="raw-markdown" v-text="markdown"></div>
</template>

<style scoped>
.data-table {
  margin: 8px 0;
}
.raw-markdown {
  padding: 12px;
  color: #999;
  font-style: italic;
}
</style>
```

- [ ] **Step 4: Write `frontend/src/components/Explanation.vue`**

```vue
<script setup lang="ts">
import { marked } from 'marked'

const props = defineProps<{ text: string }>()

const rendered = marked.parse(props.text || '')
</script>

<template>
  <div class="explanation" v-html="rendered"></div>
</template>

<style scoped>
.explanation {
  line-height: 1.7;
  font-size: 14px;
}
.explanation :deep(p) { margin: 4px 0; }
.explanation :deep(strong) { color: #333; }
</style>
```

- [ ] **Step 5: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/IntentBadge.vue frontend/src/components/SqlBlock.vue frontend/src/components/DataTable.vue frontend/src/components/Explanation.vue
git commit -m "feat(frontend): add leaf components — IntentBadge, SqlBlock, DataTable, Explanation"
```

### Task 5: ChatMessage composite component

**Files:**
- Create: `frontend/src/components/ChatMessage.vue`

**Interfaces:**
- Props: `message: DisplayMessage` (from chat store)

- [ ] **Step 1: Write `frontend/src/components/ChatMessage.vue`**

```vue
<script setup lang="ts">
import type { DisplayMessage } from '../stores/chat'
import IntentBadge from './IntentBadge.vue'
import SqlBlock from './SqlBlock.vue'
import DataTable from './DataTable.vue'
import Explanation from './Explanation.vue'

defineProps<{ message: DisplayMessage }>()
</script>

<template>
  <div class="chat-message" :class="message.role">
    <div class="message-avatar">
      {{ message.role === 'user' ? '👤' : '🤖' }}
    </div>
    <div class="message-body">
      <!-- User message: just show content -->
      <div v-if="message.role === 'user'" class="user-text">{{ message.content }}</div>

      <!-- Assistant message: full structured display -->
      <template v-else>
        <IntentBadge v-if="message.intent" :intent="message.intent" />
        <SqlBlock v-if="message.sql" :sql="message.sql" />
        <DataTable v-if="message.dataMarkdown" :markdown="message.dataMarkdown" />
        <Explanation :text="message.explanation" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.chat-message.assistant {
  background: #fafbfc;
}

.message-avatar {
  font-size: 24px;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.user-text {
  padding: 8px 12px;
  background: #e8f0fe;
  border-radius: 8px;
  display: inline-block;
  max-width: 80%;
}
</style>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatMessage.vue
git commit -m "feat(frontend): add ChatMessage composite component"
```

### Task 6: ConversationList sidebar component

**Files:**
- Create: `frontend/src/components/ConversationList.vue`

**Interfaces:**
- Consumes: `useChatStore` from Task 3

- [ ] **Step 1: Write `frontend/src/components/ConversationList.vue`**

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'

const chatStore = useChatStore()
const settingsStore = useSettingsStore()

onMounted(async () => {
  await chatStore.fetchConversations(settingsStore.activeDatabase)
})

function onSelect(id: string) {
  chatStore.selectConversation(id)
}

function onNew() {
  chatStore.newConversation()
}

function onDelete(id: string, event: Event) {
  event.stopPropagation()
  chatStore.removeConversation(id)
}
</script>

<template>
  <div class="conversation-list">
    <div class="list-header">
      <span>对话历史</span>
      <n-button size="small" type="primary" @click="onNew">+ 新建</n-button>
    </div>
    <div class="list-body">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.id"
        class="conv-item"
        :class="{ active: conv.id === chatStore.activeConversationId }"
        @click="onSelect(conv.id)"
      >
        <div class="conv-info">
          <div class="conv-title">{{ conv.title || '新对话' }}</div>
          <div class="conv-meta">
            {{ conv.database }} · {{ conv.message_count }} 条消息
          </div>
        </div>
        <n-popconfirm @positive-click="onDelete(conv.id, $event)">
          <template #trigger>
            <n-button size="tiny" text type="error">✕</n-button>
          </template>
          确定删除此对话？
        </n-popconfirm>
      </div>
      <div v-if="chatStore.conversations.length === 0" class="empty-hint">
        暂无对话，点击"+ 新建"开始
      </div>
    </div>
  </div>
</template>

<style scoped>
.conversation-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e8eaed;
  background: #fafbfc;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8eaed;
  font-weight: 600;
}
.list-body {
  flex: 1;
  overflow-y: auto;
}
.conv-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.15s;
}
.conv-item:hover { background: #e8f0fe; }
.conv-item.active { background: #d6e4ff; }
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}
.empty-hint {
  padding: 24px;
  text-align: center;
  color: #999;
  font-size: 13px;
}
</style>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConversationList.vue
git commit -m "feat(frontend): add ConversationList sidebar component"
```

### Task 7: ChatInput component

**Files:**
- Create: `frontend/src/components/ChatInput.vue`

- [ ] **Step 1: Write `frontend/src/components/ChatInput.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  send: [message: string]
}>()

const input = ref('')
const isLoading = defineProps<{ loading: boolean }>()

function onSend() {
  const msg = input.value.trim()
  if (!msg || isLoading.loading) return
  emit('send', msg)
  input.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}
</script>

<template>
  <div class="chat-input">
    <n-input
      v-model:value="input"
      type="textarea"
      placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
      :autosize="{ minRows: 1, maxRows: 4 }"
      :disabled="loading"
      @keydown="onKeydown"
    />
    <n-button
      type="primary"
      :loading="loading"
      :disabled="!input.trim()"
      @click="onSend"
    >
      发送
    </n-button>
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid #e8eaed;
  background: #fff;
  align-items: flex-end;
}
.chat-input :deep(.n-input) {
  flex: 1;
}
</style>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatInput.vue
git commit -m "feat(frontend): add ChatInput component"
```

### Task 8: LayoutHeader navigation component

**Files:**
- Create: `frontend/src/components/LayoutHeader.vue`

- [ ] **Step 1: Write `frontend/src/components/LayoutHeader.vue`**

```vue
<script setup lang="ts">
import { useSettingsStore } from '../stores/settings'

const settingsStore = useSettingsStore()

const databaseOptions = [
  { label: '测试库', value: 'test' },
  { label: '生产库', value: 'production' },
]
</script>

<template>
  <n-layout-header bordered>
    <div class="header-content">
      <div class="header-left">
        <h1 class="app-title">SAP B1 AI 助手</h1>
        <n-menu
          mode="horizontal"
          :options="[
            { label: '对话', key: 'chat' },
            { label: '校验', key: 'verify' },
            { label: '设置', key: 'settings' },
          ]"
          :value="'chat'"
          @update:value="(key: string) => $router.push({ name: key })"
        />
      </div>
      <div class="header-right">
        <n-select
          v-model:value="settingsStore.activeDatabase"
          :options="databaseOptions"
          size="small"
          style="width: 120px"
        />
      </div>
    </div>
  </n-layout-header>
</template>

<style scoped>
.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 52px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}
.app-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
  white-space: nowrap;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LayoutHeader.vue
git commit -m "feat(frontend): add LayoutHeader navigation with database selector"
```

### Task 9: ChatView page — assembles all components

**Files:**
- Create: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: Write `frontend/src/views/ChatView.vue`**

```vue
<script setup lang="ts">
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import ConversationList from '../components/ConversationList.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'

const chatStore = useChatStore()
const settingsStore = useSettingsStore()

function onSend(message: string) {
  chatStore.sendMessage(message, settingsStore.activeDatabase)
}
</script>

<template>
  <div class="chat-view">
    <aside class="sidebar" :style="{ width: settingsStore.sidebarCollapsed ? '0px' : '260px' }">
      <ConversationList />
    </aside>
    <main class="main-area">
      <div class="message-list" ref="messageListRef">
        <n-empty v-if="chatStore.messages.length === 0" description="开始一段新对话" />
        <ChatMessage
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :message="msg"
        />
        <div v-if="chatStore.error" class="error-bar">
          <n-alert type="error" :title="chatStore.error" closable />
        </div>
      </div>
      <ChatInput :loading="chatStore.isLoading" @send="onSend" />
    </main>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  height: calc(100vh - 52px);
}
.sidebar {
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s;
}
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.error-bar {
  padding: 0 16px;
}
</style>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat(frontend): add ChatView page assembling all components"
```

### Task 10: App.vue + placeholder pages + main.ts wiring

**Files:**
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/views/VerifyView.vue`
- Create: `frontend/src/views/SettingsView.vue`

- [ ] **Step 1: Write `frontend/src/main.ts`**

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import router from './router'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')
```

- [ ] **Step 2: Write `frontend/src/App.vue`**

```vue
<script setup lang="ts">
import LayoutHeader from './components/LayoutHeader.vue'
</script>

<template>
  <n-config-provider :locale="null" :theme="null">
    <n-layout>
      <LayoutHeader />
      <n-layout-content>
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-config-provider>
</template>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
#app { height: 100vh; }
</style>
```

- [ ] **Step 3: Write placeholder `frontend/src/views/VerifyView.vue`**

```vue
<template>
  <div class="placeholder-view">
    <n-empty description="数据校验功能即将上线（三期）" />
  </div>
</template>

<style scoped>
.placeholder-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 52px);
}
</style>
```

- [ ] **Step 4: Write placeholder `frontend/src/views/SettingsView.vue`**

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { testConnection, listTables } from '../api/client'
import type { TableInfo } from '../api/types'

const connectionStatus = ref<'idle' | 'testing' | 'success' | 'fail'>('idle')
const connectionMessage = ref('')
const tables = ref<TableInfo[]>([])
const tablesLoading = ref(false)

async function onTestConnection() {
  connectionStatus.value = 'testing'
  try {
    const result = await testConnection({ database: 'test' })
    connectionStatus.value = result.success ? 'success' : 'fail'
    connectionMessage.value = result.message
  } catch (e: any) {
    connectionStatus.value = 'fail'
    connectionMessage.value = e?.message || '连接失败'
  }
}

async function onLoadTables() {
  tablesLoading.value = true
  try {
    tables.value = await listTables()
  } finally {
    tablesLoading.value = false
  }
}
</script>

<template>
  <div class="settings-view">
    <n-space vertical size="large" style="max-width: 600px; padding: 24px;">
      <n-card title="数据库连接">
        <n-space align="center">
          <n-button @click="onTestConnection" :loading="connectionStatus === 'testing'">
            测试连接
          </n-button>
          <n-tag v-if="connectionStatus === 'success'" type="success">已连接</n-tag>
          <n-tag v-else-if="connectionStatus === 'fail'" type="error">连接失败</n-tag>
        </n-space>
        <p v-if="connectionMessage" style="margin-top: 12px; color: #666;">
          {{ connectionMessage }}
        </p>
      </n-card>

      <n-card title="表结构">
        <n-button @click="onLoadTables" :loading="tablesLoading">加载表列表</n-button>
        <n-table v-if="tables.length" style="margin-top: 12px;">
          <thead>
            <tr><th>表名</th><th>描述</th><th>字段数</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in tables" :key="t.name">
              <td><n-tag type="info">{{ t.name }}</n-tag></td>
              <td>{{ t.description }}</td>
              <td>{{ t.column_count }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </n-space>
  </div>
</template>

<style scoped>
.settings-view {
  height: calc(100vh - 52px);
  overflow-y: auto;
}
</style>
```

- [ ] **Step 5: Verify TypeScript + build**

```bash
cd frontend && npx vue-tsc --noEmit && npm run build
```

Expected: no type errors, `dist/` produced with no build errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/main.ts frontend/src/App.vue frontend/src/views/VerifyView.vue frontend/src/views/SettingsView.vue
git commit -m "feat(frontend): wire up App.vue, router, placeholder pages, settings page"
```

### Task 11: Fix LayoutHeader router integration

**Files:**
- Modify: `frontend/src/components/LayoutHeader.vue`

The `$router` is not automatically available in `<script setup>`. Use `useRouter` instead.

- [ ] **Step 1: Fix LayoutHeader to use useRouter**

Edit `frontend/src/components/LayoutHeader.vue`, replace the script section:

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const settingsStore = useSettingsStore()

const databaseOptions = [
  { label: '测试库', value: 'test' },
  { label: '生产库', value: 'production' },
]

function onMenuChange(key: string) {
  router.push({ name: key })
}
</script>
```

And fix the template's `@update:value` to use the method:

```vue
<n-menu
  mode="horizontal"
  :options="[...]"
  @update:value="onMenuChange"
/>
```

Also add `:default-value` to track current route:

```vue
:default-value="$route.name as string"
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npx vue-tsc --noEmit && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LayoutHeader.vue
git commit -m "fix(frontend): use useRouter instead of $router in LayoutHeader"
```

### Task 12: End-to-end verification

- [ ] **Step 1: Start backend** (if not running)

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: Start frontend dev server**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Manual verification checklist**

Open `http://localhost:5173` and verify:
- [ ] Header shows "SAP B1 AI 助手" with nav menu
- [ ] Database selector dropdown (测试库 / 生产库) works
- [ ] Left sidebar shows "对话历史" with "+ 新建" button
- [ ] Center area shows empty state "开始一段新对话"
- [ ] Type a query (e.g., "查库存") and hit Enter
- [ ] User message appears with blue bubble
- [ ] Loading spinner shows while waiting
- [ ] AI response shows: intent badge, SQL code block, data table, explanation
- [ ] New conversation appears in sidebar with title
- [ ] Click a conversation in sidebar loads its messages
- [ ] Delete button on conversation removes it
- [ ] "校验" nav goes to placeholder page
- [ ] "设置" nav shows connection test + table list
- [ ] Test connection button works
- [ ] Load tables button shows SAP B1 table list

- [ ] **Step 4: Commit if any fixes were needed**

```bash
git add -A && git commit -m "fix(frontend): end-to-end verification fixes"
```

