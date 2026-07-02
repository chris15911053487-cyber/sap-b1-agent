<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { testConnection, listTables } from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { TableInfo, ConnectionTestResponse } from '../api/types'

const settingsStore = useSettingsStore()

const connectionStatus = ref<'idle' | 'testing' | 'success' | 'fail'>('idle')
const connectionMessage = ref('')
const connectionDetail = ref<ConnectionTestResponse | null>(null)
const tables = ref<TableInfo[]>([])
const tablesLoading = ref(false)
const apiStatus = ref<'checking' | 'ok' | 'error'>('checking')

onMounted(async () => {
  try {
    const resp = await fetch('/health')
    apiStatus.value = resp.ok ? 'ok' : 'error'
  } catch {
    apiStatus.value = 'error'
  }
})

async function onTestConnection() {
  connectionStatus.value = 'testing'
  connectionDetail.value = null
  try {
    const result = await testConnection({ database: settingsStore.activeDatabase })
    connectionStatus.value = result.success ? 'success' : 'fail'
    connectionMessage.value = result.message
    connectionDetail.value = result
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
    <n-space vertical size="large" style="max-width: 700px; padding: 24px;">

      <!-- API Status -->
      <n-card title="服务状态">
        <n-space align="center">
          <n-tag v-if="apiStatus === 'ok'" type="success" size="medium">API 正常</n-tag>
          <n-tag v-else-if="apiStatus === 'error'" type="error" size="medium">API 不可用</n-tag>
          <n-tag v-else type="warning" size="medium">检查中...</n-tag>
          <n-text depth="3">目标数据库: {{ settingsStore.activeDatabase }}</n-text>
        </n-space>
      </n-card>

      <!-- Connection Test -->
      <n-card title="数据库连接">
        <n-space vertical>
          <n-space align="center">
            <n-button @click="onTestConnection" :loading="connectionStatus === 'testing'">
              测试连接
            </n-button>
            <n-tag v-if="connectionStatus === 'success'" type="success">已连接</n-tag>
            <n-tag v-else-if="connectionStatus === 'fail'" type="error">连接失败</n-tag>
          </n-space>
          <p v-if="connectionMessage" style="margin: 0; color: #666;">
            {{ connectionMessage }}
          </p>
          <n-descriptions
            v-if="connectionDetail?.success"
            label-placement="left"
            bordered
            :column="2"
            size="small"
          >
            <n-descriptions-item label="数据库">{{ connectionDetail.database }}</n-descriptions-item>
            <n-descriptions-item label="主机">{{ connectionDetail.host }}</n-descriptions-item>
            <n-descriptions-item label="端口">{{ connectionDetail.port }}</n-descriptions-item>
          </n-descriptions>
        </n-space>
      </n-card>

      <!-- Table Schema -->
      <n-card title="表结构">
        <n-space vertical>
          <n-space align="center">
            <n-button @click="onLoadTables" :loading="tablesLoading">加载表列表</n-button>
            <n-text v-if="tables.length" depth="3">共 {{ tables.length }} 张表</n-text>
          </n-space>
          <n-table v-if="tables.length" style="margin-top: 12px;" :bordered="true" :single-line="false" size="small">
            <thead>
              <tr><th>表名</th><th>描述</th><th>字段数</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in tables" :key="t.name">
                <td><n-tag type="info" size="small">{{ t.name }}</n-tag></td>
                <td>{{ t.description || '-' }}</td>
                <td>{{ t.column_count }}</td>
              </tr>
            </tbody>
          </n-table>
        </n-space>
      </n-card>

    </n-space>
  </div>
</template>

<style scoped>
.settings-view {
  height: calc(100vh - 52px);
  overflow-y: auto;
  display: flex;
  justify-content: center;
}
</style>
