<script setup lang="ts">
import { ref } from 'vue'
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
