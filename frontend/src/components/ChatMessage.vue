<script setup lang="ts">
import type { DisplayMessage } from '../stores/chat'
import IntentBadge from './IntentBadge.vue'
import SqlBlock from './SqlBlock.vue'
import DataTable from './DataTable.vue'
import Explanation from './Explanation.vue'

defineProps<{ message: DisplayMessage }>()
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
        <SqlBlock v-if="message.sql" :sql="message.sql" />
        <DataTable v-if="message.dataMarkdown" :markdown="message.dataMarkdown" />
        <Explanation :text="message.explanation" />
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
</style>
