<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const settingsStore = useSettingsStore()

const databaseOptions = computed(() =>
  settingsStore.databases.map(db => ({
    label: db.database ? `${db.name} (${db.database})` : db.name,
    value: db.name,
  }))
)

function navigate(key: string) {
  router.push({ name: key })
}

onMounted(() => {
  settingsStore.fetchDatabases()
})
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
          @update:value="navigate"
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
