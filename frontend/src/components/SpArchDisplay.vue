<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/github.css'
import type { SSESpArchEvent } from '../api/types'
import { deployStoredProcedures } from '../api/client'
import type { SpDeployResponse } from '../api/client'

hljs.registerLanguage('sql', sql)

const props = defineProps<{ data: SSESpArchEvent }>()

onErrorCaptured((err) => {
  console.error('[SpArchDisplay] render error:', err)
  return false
})

// Safely handle potentially missing fields
const procedures = computed(() => props.data?.procedures || [])
const executionOrder = computed(() => props.data?.execution_order || [])
const designNotes = computed(() => props.data?.design_notes || '')

// Editable code state — initialized from generated_code
const editableCodes = ref<Record<string, string>>({})

function getEditableCode(procName: string, originalCode: string): string {
  if (!(procName in editableCodes.value)) {
    editableCodes.value[procName] = originalCode || ''
  }
  return editableCodes.value[procName]
}

function updateCode(procName: string, event: Event) {
  const target = event.target as HTMLTextAreaElement
  editableCodes.value[procName] = target.value
}

// Editing mode per procedure
const editingStates = ref<Record<string, boolean>>({})

function toggleEdit(procName: string, code: string) {
  if (!editingStates.value[procName]) {
    // Entering edit mode — init the editable code if needed
    getEditableCode(procName, code)
  }
  editingStates.value[procName] = !editingStates.value[procName]
}

// Deploy state
const isDeploying = ref(false)
const deployResponse = ref<SpDeployResponse | null>(null)
const deployError = ref<string | null>(null)

async function handleDeploy() {
  isDeploying.value = true
  deployError.value = null
  deployResponse.value = null

  try {
    const proceduresInput = procedures.value.map(proc => ({
      name: proc.name,
      generated_code: editableCodes.value[proc.name] || proc.generated_code,
      dependencies: proc.dependencies || [],
      parameters: proc.parameters || {},
    }))

    const response = await deployStoredProcedures({
      procedures: proceduresInput,
      execution_order: executionOrder.value,
    })

    deployResponse.value = response
  } catch (e: any) {
    deployError.value = e?.response?.data?.detail || e?.message || '部署请求失败'
  } finally {
    isDeploying.value = false
  }
}

function highlightCode(code: string): string {
  if (!code) return ''
  try {
    return hljs.highlight(code, { language: 'sql' }).value
  } catch {
    return code
  }
}

const copiedStates = ref<Record<string, boolean>>({})

async function handleCopy(procName: string) {
  const code = editableCodes.value[procName] || procedures.value.find(p => p.name === procName)?.generated_code || ''
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    await navigator.clipboard.writeText(code)
  } else {
    const textarea = document.createElement('textarea')
    textarea.value = code
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  copiedStates.value[procName] = true
  setTimeout(() => { copiedStates.value[procName] = false }, 2000)
}

function statusColor(_name: string): string {
  return '#2080f0'
}

function getDeployResultIcon(name: string): string {
  if (!deployResponse.value) return ''
  const r = deployResponse.value.deploy_results.find(r => r.name === name)
  if (!r) return ''
  return r.success ? '✅' : '❌'
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
            <n-h4 class="proc-name">
              <span>{{ getDeployResultIcon(proc.name) }}</span>
              {{ proc.name }}
            </n-h4>
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

      <!-- T-SQL Code — Always visible, editable -->
      <div v-if="proc.generated_code" class="code-section">
        <div class="code-header">
          <span class="code-label">{{ proc.name }}.sql</span>
          <div class="code-actions">
            <n-button size="tiny" text @click="handleCopy(proc.name)">
              {{ copiedStates[proc.name] ? '已复制 ✓' : '复制' }}
            </n-button>
            <n-button
              size="tiny"
              :type="editingStates[proc.name] ? 'primary' : 'default'"
              @click="toggleEdit(proc.name, proc.generated_code)"
            >
              {{ editingStates[proc.name] ? '预览' : '编辑' }}
            </n-button>
          </div>
        </div>

        <!-- Edit mode: textarea -->
        <textarea
          v-if="editingStates[proc.name]"
          class="code-editor"
          :value="getEditableCode(proc.name, proc.generated_code)"
          @input="updateCode(proc.name, $event)"
          spellcheck="false"
        />

        <!-- Preview mode: highlighted code -->
        <pre v-else class="code-preview"><code class="language-sql" v-html="highlightCode(getEditableCode(proc.name, proc.generated_code))"></code></pre>
      </div>
    </n-card>

    <!-- Deploy Button & Results -->
    <div class="deploy-section">
      <n-button
        type="primary"
        size="large"
        :loading="isDeploying"
        :disabled="isDeploying || procedures.length === 0"
        @click="handleDeploy"
      >
        🚀 确认部署全部存储过程
      </n-button>

      <n-alert v-if="deployError" type="error" :title="deployError" class="deploy-alert" closable />

      <!-- Deploy Results -->
      <n-card v-if="deployResponse" class="deploy-result-card" :bordered="true" size="small">
        <template #header>
          <div class="section-header">
            <span class="section-icon">🚀</span>
            <span class="section-title">部署结果</span>
            <n-tag
              :type="deployResponse.deploy_failed === 0 ? 'success' : 'warning'"
              size="small"
            >
              {{ deployResponse.deploy_succeeded }}/{{ deployResponse.deploy_total }} 成功
            </n-tag>
          </div>
        </template>

        <div v-if="deployResponse.log_table_created" class="log-notice">
          <n-tag size="tiny" type="info">已自动创建 ZZ_SP_LOG 日志表</n-tag>
        </div>

        <div class="result-list">
          <div
            v-for="r in deployResponse.deploy_results"
            :key="r.name"
            class="result-item"
            :class="{ success: r.success, failed: !r.success }"
          >
            <span class="result-icon">{{ r.success ? '✅' : '❌' }}</span>
            <span class="result-name">{{ r.name }}</span>
            <n-tag size="tiny" :type="r.action === 'created' ? 'success' : r.action === 'replaced' ? 'info' : 'error'">
              {{ r.action === 'created' ? '新建' : r.action === 'replaced' ? '替换' : r.action === 'skipped' ? '跳过' : '失败' }}
            </n-tag>
            <span class="result-time">{{ r.execution_time_ms.toFixed(0) }}ms</span>
            <n-text v-if="r.error" depth="3" class="result-error">{{ r.error }}</n-text>
          </div>
        </div>

        <!-- Verify Results -->
        <div v-if="deployResponse.verify_total > 0" class="verify-section">
          <n-divider />
          <div class="section-header">
            <span class="section-icon">🧪</span>
            <span class="section-title">验证结果</span>
            <n-tag
              :type="deployResponse.verify_failed === 0 ? 'success' : 'warning'"
              size="small"
            >
              {{ deployResponse.verify_passed }}/{{ deployResponse.verify_total }} 通过
            </n-tag>
          </div>
          <div class="result-list">
            <div
              v-for="r in deployResponse.verify_results"
              :key="r.name"
              class="result-item"
              :class="{ success: r.success, failed: !r.success }"
            >
              <span class="result-icon">{{ r.success ? '✅' : '❌' }}</span>
              <span class="result-name">{{ r.name }}</span>
              <n-tag v-if="r.success" size="tiny" type="success">{{ r.row_count }} 行</n-tag>
              <span class="result-time">{{ r.execution_time_ms.toFixed(0) }}ms</span>
              <n-text v-if="r.error" depth="3" class="result-error">{{ r.error }}</n-text>
            </div>
          </div>
        </div>
      </n-card>
    </div>
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

/* Code section - always visible */
.code-section {
  margin-top: 12px;
  border-radius: 6px;
  overflow: hidden;
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
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

.code-actions {
  display: flex;
  gap: 8px;
}

.code-editor {
  width: 100%;
  min-height: 300px;
  max-height: 600px;
  padding: 12px;
  border: none;
  outline: none;
  resize: vertical;
  font-family: 'Courier New', 'Menlo', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  background: #1e1e1e;
  color: #d4d4d4;
  tab-size: 4;
  white-space: pre;
  overflow: auto;
}

.code-preview {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
}

/* Deploy section */
.deploy-section {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.deploy-alert {
  width: 100%;
}

.deploy-result-card {
  width: 100%;
  border-left: 3px solid #18a058;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 16px;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.log-notice {
  margin-bottom: 8px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 13px;
  flex-wrap: wrap;
}

.result-item.success {
  background: #f6ffed;
}

.result-item.failed {
  background: #fff2f0;
}

.result-icon {
  flex-shrink: 0;
}

.result-name {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  font-weight: 500;
}

.result-time {
  margin-left: auto;
  font-size: 11px;
  color: #999;
}

.result-error {
  font-size: 11px;
  width: 100%;
  color: #ff4d4f;
  margin-top: 2px;
}

.verify-section {
  margin-top: 8px;
}
</style>
