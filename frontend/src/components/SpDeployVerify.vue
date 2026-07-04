<script setup lang="ts">
import type { SSESpDeployEvent, SSESpVerifyEvent } from '../api/types'

defineProps<{
  deployData?: SSESpDeployEvent
  verifyData?: SSESpVerifyEvent
}>()
</script>

<template>
  <div class="sp-deploy-verify">
    <!-- Deploy Results -->
    <n-card v-if="deployData" class="deploy-card" :bordered="true" size="small">
      <template #header>
        <div class="section-header">
          <span class="section-icon">🚀</span>
          <span class="section-title">部署结果</span>
          <n-tag
            :type="deployData.failed === 0 ? 'success' : 'warning'"
            size="small"
          >
            {{ deployData.succeeded }}/{{ deployData.total }} 成功
          </n-tag>
        </div>
      </template>

      <div v-if="deployData.log_table_created" class="log-notice">
        <n-tag size="tiny" type="info">已自动创建 ZZ_SP_LOG 日志表</n-tag>
      </div>

      <div class="result-list">
        <div
          v-for="r in deployData.results"
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
    </n-card>

    <!-- Verify Results -->
    <n-card v-if="verifyData" class="verify-card" :bordered="true" size="small">
      <template #header>
        <div class="section-header">
          <span class="section-icon">🧪</span>
          <span class="section-title">验证结果</span>
          <n-tag
            :type="verifyData.failed === 0 ? 'success' : 'warning'"
            size="small"
          >
            {{ verifyData.passed }}/{{ verifyData.total }} 通过
          </n-tag>
        </div>
      </template>

      <div class="result-list">
        <div
          v-for="r in verifyData.results"
          :key="r.name"
          class="result-item"
          :class="{ success: r.success, failed: !r.success }"
        >
          <span class="result-icon">{{ r.success ? '✅' : '❌' }}</span>
          <span class="result-name">{{ r.name }}</span>
          <n-tag v-if="r.success" size="tiny" type="success">
            {{ r.row_count }} 行
          </n-tag>
          <span class="result-time">{{ r.execution_time_ms.toFixed(0) }}ms</span>
          <n-text v-if="r.error" depth="3" class="result-error">{{ r.error }}</n-text>
        </div>
      </div>

      <!-- Sample output for passed verifications -->
      <n-collapse v-if="verifyData.results.some(r => r.sample_output)" class="sample-collapse">
        <n-collapse-item
          v-for="r in verifyData.results.filter(r => r.sample_output)"
          :key="r.name"
          :title="`${r.name} 示例输出`"
          :name="r.name"
        >
          <pre class="sample-output">{{ r.sample_output }}</pre>
        </n-collapse-item>
      </n-collapse>
    </n-card>
  </div>
</template>

<style scoped>
.sp-deploy-verify {
  margin: 8px 0;
}

.deploy-card {
  margin-bottom: 8px;
  border-left: 3px solid #18a058;
}

.verify-card {
  margin-bottom: 8px;
  border-left: 3px solid #2080f0;
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
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 13px;
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
  margin-left: 8px;
  color: #ff4d4f;
}

.sample-collapse {
  margin-top: 8px;
}

.sample-output {
  background: #f6f8fa;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Courier New', monospace;
  overflow-x: auto;
  white-space: pre;
  line-height: 1.4;
  margin: 0;
}
</style>
