<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/github.css'
import type { SSESpArchEvent } from '../api/types'
import type { SpValidateResponse, SpRepairResponse, ValidationReportItem, VerificationCheckDef } from '../api/types'
import { deployStoredProcedures, updateMessageData, validateStoredProcedures, repairStoredProcedure } from '../api/client'
import type { SpDeployResponse } from '../api/client'

hljs.registerLanguage('sql', sql)

const props = defineProps<{
  data: SSESpArchEvent
  messageId: string
  conversationId: string
}>()

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

// Save state
const isSaving = ref(false)
const saveSuccess = ref(false)
const saveError = ref<string | null>(null)

async function handleSave() {
  if (!props.conversationId || !props.messageId) {
    saveError.value = '无法保存：缺少对话信息'
    return
  }

  isSaving.value = true
  saveError.value = null
  saveSuccess.value = false

  try {
    // Build updated sp_arch data with edited codes
    const updatedData = {
      ...props.data,
      procedures: procedures.value.map(proc => ({
        ...proc,
        generated_code: editableCodes.value[proc.name] || proc.generated_code,
      })),
    }

    await updateMessageData(
      props.conversationId,
      props.messageId,
      JSON.stringify(updatedData),
    )

    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (e: any) {
    saveError.value = e?.response?.data?.error?.message || e?.message || '保存失败'
  } finally {
    isSaving.value = false
  }
}

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

// ---------------------------------------------------------------------------
// 业务对账验证 + AI 自修复
// ---------------------------------------------------------------------------

// 是否有任何 SP 配置了业务对账断言
const hasVerificationChecks = computed(() =>
  procedures.value.some(p => (p.verification_checks?.length || 0) > 0)
)

const isValidating = ref(false)
const validateResponse = ref<SpValidateResponse | null>(null)
const validateError = ref<string | null>(null)

// 每个 SP 的修复状态
const repairingState = ref<Record<string, boolean>>({})
const repairResults = ref<Record<string, SpRepairResponse>>({})
const repairError = ref<Record<string, string>>({})

async function handleValidate() {
  isValidating.value = true
  validateError.value = null
  validateResponse.value = null

  try {
    const input = procedures.value
      .filter(p => (p.verification_checks?.length || 0) > 0)
      .map(p => ({
        name: p.name,
        verification_checks: (p.verification_checks || []) as VerificationCheckDef[],
      }))

    validateResponse.value = await validateStoredProcedures(input)
  } catch (e: any) {
    validateError.value = e?.response?.data?.error?.message || e?.message || '验证请求失败'
  } finally {
    isValidating.value = false
  }
}

async function handleRepair(spName: string) {
  const proc = procedures.value.find(p => p.name === spName)
  if (!proc) return

  repairingState.value[spName] = true
  repairError.value[spName] = ''

  try {
    const result = await repairStoredProcedure(
      {
        name: proc.name,
        description: proc.description,
        output_table: proc.output_table,
        business_logic: proc.business_logic,
        parameters: proc.parameters || {},
        generated_code: editableCodes.value[proc.name] || proc.generated_code,
        verification_checks: (proc.verification_checks || []) as VerificationCheckDef[],
      },
      undefined,
      3,
    )
    repairResults.value[spName] = result

    // 修复成功后，用最终代码更新可编辑代码
    if (result.success && result.final_code) {
      editableCodes.value[spName] = result.final_code
    }
    // 用修复得到的 final_report 覆盖展示
    if (validateResponse.value && result.final_report && 'sp_name' in result.final_report) {
      const idx = validateResponse.value.reports.findIndex(r => r.sp_name === spName)
      const finalReport = result.final_report as ValidationReportItem
      if (idx !== -1) {
        validateResponse.value.reports[idx] = finalReport
      } else {
        validateResponse.value.reports.push(finalReport)
      }
    }
  } catch (e: any) {
    repairError.value[spName] = e?.response?.data?.error?.message || e?.message || '修复请求失败'
  } finally {
    repairingState.value[spName] = false
  }
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
      <div class="action-buttons">
        <n-button
          type="primary"
          size="large"
          :loading="isDeploying"
          :disabled="isDeploying || procedures.length === 0"
          @click="handleDeploy"
        >
          🚀 确认部署全部存储过程
        </n-button>
        <n-button
          size="large"
          :loading="isSaving"
          :disabled="isSaving"
          @click="handleSave"
        >
          💾 保存修改
        </n-button>
        <n-button
          v-if="hasVerificationChecks"
          type="info"
          size="large"
          :loading="isValidating"
          :disabled="isValidating"
          @click="handleValidate"
        >
          🔍 运行业务对账验证
        </n-button>
      </div>

      <n-alert v-if="saveSuccess" type="success" title="保存成功 — 刷新页面后仍可看到修改" class="deploy-alert" closable />
      <n-alert v-if="saveError" type="error" :title="saveError" class="deploy-alert" closable />
      <n-alert v-if="deployError" type="error" :title="deployError" class="deploy-alert" closable />
      <n-alert v-if="validateError" type="error" :title="validateError" class="deploy-alert" closable />

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
              <!-- Sample output data preview -->
              <pre v-if="r.sample_output" class="sample-output">{{ r.sample_output }}</pre>
            </div>
          </div>
        </div>
      </n-card>

      <!-- 业务对账验证结果 -->
      <n-card v-if="validateResponse" class="validate-result-card" :bordered="true" size="small">
        <template #header>
          <div class="section-header">
            <span class="section-icon">🔍</span>
            <span class="section-title">业务对账验证</span>
            <n-tag
              :type="validateResponse.has_error_failures ? 'error' : (validateResponse.total_failed > 0 ? 'warning' : 'success')"
              size="small"
            >
              {{ validateResponse.total_passed }}/{{ validateResponse.total_checks }} 通过
            </n-tag>
          </div>
        </template>

        <div v-if="validateResponse.reports.length === 0" class="empty-hint">
          <n-text depth="3">没有可运行的业务对账断言</n-text>
        </div>

        <!-- 每个 SP 的验证报告 -->
        <div v-for="report in validateResponse.reports" :key="report.sp_name" class="sp-report">
          <div class="sp-report-header">
            <span class="sp-report-icon">{{ report.has_error_failures ? '❌' : (report.failed > 0 ? '⚠️' : '✅') }}</span>
            <span class="sp-report-name">{{ report.sp_name }}</span>
            <n-tag size="tiny" :type="report.has_error_failures ? 'error' : (report.failed > 0 ? 'warning' : 'success')">
              {{ report.passed }}/{{ report.total }} 通过
            </n-tag>
            <!-- AI 自动修复按钮 -->
            <n-button
              v-if="report.has_error_failures"
              size="tiny"
              type="warning"
              class="repair-btn"
              :loading="repairingState[report.sp_name]"
              :disabled="repairingState[report.sp_name]"
              @click="handleRepair(report.sp_name)"
            >
              🤖 让 AI 自动修复
            </n-button>
          </div>

          <!-- 每条断言结果 -->
          <div class="check-list">
            <div
              v-for="check in report.results"
              :key="check.name"
              class="check-item"
              :class="{ passed: check.passed, failed: !check.passed }"
            >
              <div class="check-row">
                <span class="check-icon">{{ check.passed ? '✅' : (check.severity === 'error' ? '❌' : '⚠️') }}</span>
                <span class="check-name">{{ check.name }}</span>
                <n-tag size="tiny" :bordered="false">{{ check.category }}</n-tag>
                <n-tag v-if="check.severity === 'warning'" size="tiny" type="warning" :bordered="false">warning</n-tag>
              </div>
              <div v-if="check.description" class="check-desc">{{ check.description }}</div>
              <div class="check-detail" :class="{ 'detail-fail': !check.passed }">{{ check.detail }}</div>
              <div v-if="check.assertion" class="check-assertion">
                <code>期望: {{ check.assertion }}</code>
              </div>
            </div>
          </div>

          <!-- 修复错误提示 -->
          <n-alert v-if="repairError[report.sp_name]" type="error" :title="repairError[report.sp_name]" class="deploy-alert" closable />

          <!-- 修复迭代过程 -->
          <div v-if="repairResults[report.sp_name]" class="repair-result">
            <n-divider dashed />
            <div class="repair-header">
              <span>{{ repairResults[report.sp_name].success ? '✅' : '⚠️' }}</span>
              <span class="repair-message">{{ repairResults[report.sp_name].message }}</span>
            </div>
            <n-collapse>
              <n-collapse-item
                v-for="it in repairResults[report.sp_name].iterations"
                :key="it.iteration"
                :title="`第 ${it.iteration} 次修复 ${it.passed ? '✅ 通过' : (it.deploy_success ? '❌ 仍未通过' : '部署失败')}`"
                :name="it.iteration"
              >
                <div v-if="it.llm_error" class="repair-err">AI 生成失败: {{ it.llm_error }}</div>
                <div v-if="it.deploy_error" class="repair-err">部署错误: {{ it.deploy_error }}</div>
                <div v-if="it.validation_report && it.validation_report.results" class="repair-checks">
                  <div
                    v-for="c in it.validation_report.results"
                    :key="c.name"
                    class="check-mini"
                    :class="{ passed: c.passed, failed: !c.passed }"
                  >
                    {{ c.passed ? '✅' : '❌' }} {{ c.name }} — {{ c.detail }}
                  </div>
                </div>
                <pre v-if="it.generated_code" class="code-preview repair-code"><code class="language-sql" v-html="highlightCode(it.generated_code)"></code></pre>
              </n-collapse-item>
            </n-collapse>
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

.action-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
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

.sample-output {
  width: 100%;
  margin-top: 6px;
  padding: 8px 12px;
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  font-family: 'Courier New', 'Menlo', monospace;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
  color: #333;
}

/* 业务对账验证 */
.validate-result-card {
  width: 100%;
  border-left: 3px solid #2080f0;
  margin-top: 12px;
}

.empty-hint {
  padding: 8px 0;
}

.sp-report {
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  background: #fafbfc;
}

.sp-report-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.sp-report-name {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  font-size: 13px;
}

.repair-btn {
  margin-left: auto;
}

.check-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.check-item {
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 3px solid #d0d7de;
}

.check-item.passed {
  background: #f6ffed;
  border-left-color: #52c41a;
}

.check-item.failed {
  background: #fff2f0;
  border-left-color: #ff4d4f;
}

.check-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.check-name {
  font-weight: 500;
  font-size: 13px;
}

.check-desc {
  font-size: 12px;
  color: #666;
  margin-top: 2px;
}

.check-detail {
  font-size: 12px;
  color: #444;
  margin-top: 2px;
}

.check-detail.detail-fail {
  color: #d4380d;
  font-weight: 500;
}

.check-assertion {
  margin-top: 2px;
  font-size: 11px;
  color: #888;
}

.repair-result {
  margin-top: 8px;
}

.repair-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.repair-message {
  color: #444;
}

.repair-err {
  color: #ff4d4f;
  font-size: 12px;
  margin: 4px 0;
}

.check-mini {
  font-size: 12px;
  padding: 2px 0;
}

.check-mini.failed {
  color: #d4380d;
}

.repair-code {
  margin-top: 8px;
}
</style>
