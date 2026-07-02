<script setup lang="ts">
import type { VerifyFindingItem } from '../api/types'

const props = defineProps<{
  finding: VerifyFindingItem
}>()

const statusConfig: Record<string, { type: 'success' | 'error' | 'warning'; icon: string; label: string }> = {
  pass: { type: 'success', icon: '✅', label: '通过' },
  fail: { type: 'error', icon: '❌', label: '异常' },
  error: { type: 'warning', icon: '⚠️', label: '错误' },
}
const config = statusConfig[props.finding.status] || statusConfig.error
</script>

<template>
  <n-card :bordered="true" size="small" class="verify-card">
    <template #header>
      <div class="card-header">
        <span class="icon">{{ config.icon }}</span>
        <span class="name">{{ finding.check_name }}</span>
        <n-tag :type="config.type" size="small">{{ config.label }}</n-tag>
      </div>
    </template>
    <p class="detail">{{ finding.detail }}</p>
  </n-card>
</template>

<style scoped>
.verify-card {
  margin-bottom: 12px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.icon {
  font-size: 18px;
}
.name {
  flex: 1;
  font-weight: 500;
}
.detail {
  color: #666;
  margin: 0;
  font-size: 14px;
}
</style>
