<script setup lang="ts">
import { watch } from 'vue'
import type { DisplayMessage } from '../stores/chat'
import IntentBadge from './IntentBadge.vue'
import SpArchDisplay from './SpArchDisplay.vue'
import SqlBlock from './SqlBlock.vue'
import DataTable from './DataTable.vue'
import Explanation from './Explanation.vue'

const props = defineProps<{ message: DisplayMessage }>()

watch(() => props.message.spArchData, (val) => {
  console.log('[ChatMessage] spArchData changed:', val ? `yes (${val.name}, ${val.procedures?.length} procs)` : 'no')
}, { immediate: true })
</script>

<template>
  <div class="chat-message" :class="message.role">
    <div class="message-avatar">
      {{ message.role === 'user' ? '👤' : '🤖' }}
    </div>
    <div class="message-body">
      <!-- User message: just show content -->
      <div v-if="message.role === 'user'" class="user-text">{{ message.content }}</div>

      <!-- Assistant message: full structured display -->
      <template v-else>
        <IntentBadge v-if="message.intent" :intent="message.intent" />
        <SpArchDisplay v-if="message.spArchData" :data="message.spArchData" />
        <SqlBlock v-if="message.sql" :sql="message.sql" />
        <DataTable v-if="message.dataMarkdown" :markdown="message.dataMarkdown" />
        <Explanation v-if="message.explanation" :text="message.explanation" />
        <!-- Show raw content when no structured data has arrived yet (e.g. progress/status messages) -->
        <div v-if="!message.sql && !message.dataMarkdown && !message.spArchData && !message.explanation && message.content"
             class="assistant-status">{{ message.content }}</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.chat-message.assistant {
  background: #fafbfc;
}

.message-avatar {
  font-size: 24px;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.user-text {
  padding: 8px 12px;
  background: #e8f0fe;
  border-radius: 8px;
  display: inline-block;
  max-width: 80%;
}

.assistant-status {
  color: #888;
  font-size: 13px;
  padding: 4px 0;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
