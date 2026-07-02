<script setup lang="ts">
import { ref } from 'vue'
import { runVerification } from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { VerifyResponse } from '../api/types'
import VerifyCard from '../components/VerifyCard.vue'

const settingsStore = useSettingsStore()
const isLoading = ref(false)
const result = ref<VerifyResponse | null>(null)
const error = ref<string | null>(null)

async function onRunVerify() {
  isLoading.value = true
  error.value = null
  result.value = null
  try {
    result.value = await runVerification(settingsStore.activeDatabase)
  } catch (e: any) {
    error.value = e?.message || '验证失败'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="verify-view">
    <div class="verify-content">
      <n-space vertical size="large" style="max-width: 800px; padding: 24px;">
        <n-card title="数据校验">
          <template #header-extra>
            <n-button
              type="primary"
              :loading="isLoading"
              @click="onRunVerify"
            >
              执行全部校验
            </n-button>
          </template>

          <n-space vertical>
            <n-text depth="3">
              当前数据库: <n-tag type="info" size="small">{{ settingsStore.activeDatabase }}</n-tag>
            </n-text>

            <n-alert v-if="error" type="error" :title="error" closable />

            <div v-if="result" class="result-summary">
              <n-space align="center">
                <n-statistic label="总检查项" :value="result.total_checks" />
                <n-statistic label="通过">
                  <span class="stat-pass">{{ result.passed }}</span>
                </n-statistic>
                <n-statistic label="异常">
                  <span class="stat-fail">{{ result.failed }}</span>
                </n-statistic>
                <n-statistic label="通过率">
                  <span :class="result.pass_rate >= 0.8 ? 'stat-pass' : 'stat-fail'">
                    {{ (result.pass_rate * 100).toFixed(0) }}%
                  </span>
                </n-statistic>
              </n-space>
            </div>

            <div v-if="result">
              <VerifyCard
                v-for="finding in result.findings"
                :key="finding.check_name"
                :finding="finding"
              />
            </div>

            <n-empty
              v-if="!result && !error"
              description="点击「执行全部校验」开始数据验证"
            />
          </n-space>
        </n-card>
      </n-space>
    </div>
  </div>
</template>

<style scoped>
.verify-view {
  height: calc(100vh - 52px);
  overflow-y: auto;
}
.verify-content {
  display: flex;
  justify-content: center;
}
.result-summary {
  margin-bottom: 16px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}
.stat-pass { color: #18a058; font-weight: 600; }
.stat-fail { color: #d03050; font-weight: 600; }
</style>
