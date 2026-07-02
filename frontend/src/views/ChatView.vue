<script setup lang="ts">
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import ConversationList from '../components/ConversationList.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'

const chatStore = useChatStore()
const settingsStore = useSettingsStore()

function onSend(message: string) {
  chatStore.sendMessage(message, settingsStore.activeDatabase)
}
</script>

<template>
  <div class="chat-view">
    <aside class="sidebar" :style="{ width: settingsStore.sidebarCollapsed ? '0px' : '260px' }">
      <ConversationList />
    </aside>
    <main class="main-area">
      <div class="message-list" ref="messageListRef">
        <n-empty v-if="chatStore.messages.length === 0" description="开始一段新对话" />
        <ChatMessage
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :message="msg"
        />
        <div v-if="chatStore.error" class="error-bar">
          <n-alert type="error" :title="chatStore.error" closable />
        </div>
      </div>
      <ChatInput :loading="chatStore.isLoading" @send="onSend" />
    </main>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  height: calc(100vh - 52px);
}
.sidebar {
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s;
}
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.error-bar {
  padding: 0 16px;
}
</style>
