import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listDatabases } from '../api/client'
import type { DatabaseInfo } from '../api/types'

export const useSettingsStore = defineStore('settings', () => {
  const activeDatabase = ref<string>('test')
  const sidebarCollapsed = ref(false)
  const databases = ref<DatabaseInfo[]>([])
  const databasesLoading = ref(false)

  function setDatabase(db: string) {
    activeDatabase.value = db
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  async function fetchDatabases() {
    databasesLoading.value = true
    try {
      databases.value = await listDatabases()
      // Auto-select first database if current selection not in list
      if (databases.value.length > 0 &&
          !databases.value.find(d => d.name === activeDatabase.value)) {
        activeDatabase.value = databases.value[0].name
      }
    } catch {
      // Keep hardcoded fallback
      databases.value = [
        { name: 'test', host: '', port: 0, database: '' },
        { name: 'production', host: '', port: 0, database: '' },
      ]
    } finally {
      databasesLoading.value = false
    }
  }

  return { activeDatabase, sidebarCollapsed, databases, databasesLoading, setDatabase, toggleSidebar, fetchDatabases }
})
