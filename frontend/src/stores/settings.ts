import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  const activeDatabase = ref<string>('test')
  const sidebarCollapsed = ref(false)

  function setDatabase(db: string) {
    activeDatabase.value = db
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { activeDatabase, sidebarCollapsed, setDatabase, toggleSidebar }
})
