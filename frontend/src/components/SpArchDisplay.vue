<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/github.css'
import type { SSESpArchEvent } from '../api/types'

hljs.registerLanguage('sql', sql)

const props = defineProps<{ data: SSESpArchEvent }>()

onErrorCaptured((err) => {
  console.error('[SpArchDisplay] render error:', err)
  return false // prevent propagation
})

console.log('[SpArchDisplay] mounting with data:', props.data?.name, 'procedures:', props.data?.procedures?.length)

// Safely handle potentially missing fields
const procedures = computed(() => props.data?.procedures || [])
const executionOrder = computed(() => props.data?.execution_order || [])
const designNotes = computed(() => props.data?.design_notes || '')

function highlightCode(code: string): string {
  if (!code) return ''
  try {
    return hljs.highlight(code, { language: 'sql' }).value
  } catch {
    return code
  }
}

function copyCode(code: string): Promise<void> {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    return navigator.clipboard.writeText(code)
  }
  // Fallback for non-secure contexts
  const textarea = document.createElement('textarea')
  textarea.value = code
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
  return Promise.resolve()
}

const copiedStates = ref<Record<string, boolean>>({})

async function handleCopy(procName: string, code: string) {
  await copyCode(code)
  copiedStates.value[procName] = true
  setTimeout(() => {
    copiedStates.value[procName] = false
  }, 2000)
}

function statusColor(_name: string): string {
  return '#2080f0'
}
</script>

<template>
  <div class="sp-arch-display">
    <!-- Overview Card -->
    <n-card class="overview-card" :bordered="true" size="small">
      <template #header>
        <div class="overview-header">
          <n-h3 class="overview-title">{{ data.name }}</n-h3>
          <n-tag type="info" size="small">共 {{ procedures.length }} 个存储过程</n-tag>
        </div>
      </template>

      <n-p class="overview-desc">{{ data.description }}</n-p>

      <n-collapse v-if="designNotes" class="design-notes-collapse">
        <n-collapse-item title="设计说明" name="design-notes">
          <n-p class="design-notes-text">{{ designNotes }}</n-p>
        </n-collapse-item>
      </n-collapse>

      <div v-if="executionOrder.length > 0" class="exec-order-section">
        <n-text strong>执行顺序</n-text>
        <n-steps :current="executionOrder.length" size="small" class="exec-steps">
          <n-step
            v-for="(name, idx) in executionOrder"
            :key="name"
            :title="`第 ${idx + 1} 步`"
            :description="name"
          />
        </n-steps>
      </div>
    </n-card>

    <n-divider />

    <!-- Per-Procedure Cards -->
    <n-card
      v-for="(proc, idx) in procedures"
      :key="proc.name"
      class="procedure-card"
      :bordered="true"
      size="small"
    >
      <template #header>
        <div class="proc-card-header">
          <div class="proc-title-row">
            <n-h4 class="proc-name">{{ proc.name }}</n-h4>
            <n-tag :bordered="false" size="tiny" :color="{ color: statusColor(proc.name), textColor: '#fff' }">
              步骤 {{ idx + 1 }}
            </n-tag>
          </div>
          <n-text depth="2" class="proc-desc">{{ proc.description }}</n-text>
        </div>
      </template>

      <!-- Dependencies -->
      <div class="proc-meta">
        <div class="meta-row">
          <span class="meta-label">依赖:</span>
          <span v-if="proc.dependencies && proc.dependencies.length > 0">
            <n-tag
              v-for="dep in proc.dependencies"
              :key="dep"
              size="tiny"
              type="warning"
              class="dep-tag"
            >
              {{ dep }}
            </n-tag>
          </span>
          <n-text v-else depth="3">无</n-text>
        </div>

        <!-- Output Table -->
        <div class="meta-row">
          <span class="meta-label">输出表:</span>
          <n-tag v-if="proc.output_table" size="tiny" type="success">
            {{ proc.output_table }}
          </n-tag>
          <n-text v-else depth="3">无</n-text>
        </div>

        <!-- Parameters -->
        <div v-if="proc.parameters && Object.keys(proc.parameters).length > 0" class="meta-row">
          <span class="meta-label">参数:</span>
          <n-table :single-line="true" size="small" class="params-table">
            <thead>
              <tr>
                <th>参数名</th>
                <th>类型</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(_type, pname) in proc.parameters" :key="pname">
                <td><n-text code>{{ pname }}</n-text></td>
                <td><n-text depth="2">{{ _type }}</n-text></td>
              </tr>
            </tbody>
          </n-table>
        </div>
      </div>

      <!-- Business Logic (collapsible) -->
      <n-collapse v-if="proc.business_logic" class="proc-collapse">
        <n-collapse-item title="业务逻辑" name="logic">
          <n-p class="business-logic-text">{{ proc.business_logic }}</n-p>
        </n-collapse-item>
      </n-collapse>

      <!-- T-SQL Code (collapsible) -->
      <n-collapse v-if="proc.generated_code" class="proc-collapse">
        <n-collapse-item title="T-SQL 代码" name="code">
          <div class="code-block">
            <div class="code-header">
              <span class="code-label">{{ proc.name }}.sql</span>
              <n-button size="tiny" text @click="handleCopy(proc.name, proc.generated_code)">
                {{ copiedStates[proc.name] ? '已复制' : '复制代码' }}
              </n-button>
            </div>
            <pre><code class="language-sql" v-html="highlightCode(proc.generated_code)"></code></pre>
          </div>
        </n-collapse-item>
      </n-collapse>
    </n-card>
  </div>
</template>

<style scoped>
.sp-arch-display {
  margin: 12px 0;
}

.overview-card {
  border-left: 3px solid #f0a020;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.overview-title {
  margin: 0;
  font-size: 16px;
}

.overview-desc {
  margin: 8px 0;
  color: #555;
}

.design-notes-collapse {
  margin: 8px 0;
}

.design-notes-text {
  white-space: pre-wrap;
  color: #666;
  font-size: 13px;
}

.exec-order-section {
  margin-top: 12px;
}

.exec-steps {
  margin-top: 8px;
}

.procedure-card {
  margin-bottom: 12px;
  border-left: 3px solid #2080f0;
}

.proc-card-header {
  width: 100%;
}

.proc-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.proc-name {
  margin: 0;
  font-size: 14px;
  font-family: 'Courier New', monospace;
}

.proc-desc {
  margin-top: 4px;
  font-size: 13px;
}

.proc-meta {
  margin: 8px 0;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}

.meta-label {
  font-weight: 600;
  color: #666;
  min-width: 56px;
}

.dep-tag {
  margin-right: 4px;
}

.params-table {
  margin-top: 4px;
  max-width: 400px;
}

.proc-collapse {
  margin-top: 8px;
}

.business-logic-text {
  white-space: pre-wrap;
  color: #555;
  font-size: 13px;
}

.code-block {
  border-radius: 6px;
  overflow: hidden;
  background: #f6f8fa;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #e8eaed;
  font-size: 12px;
}

.code-label {
  font-weight: 600;
  color: #666;
  font-family: 'Courier New', monospace;
}

.code-block pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
}
</style>
