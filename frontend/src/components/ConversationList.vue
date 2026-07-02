<script setup lang="ts">
import { onMounted } from 'vue'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'

const chatStore = useChatStore()
const settingsStore = useSettingsStore()

onMounted(async () => {
  await chatStore.fetchConversations(settingsStore.activeDatabase)
})

function onSelect(id: string) {
  chatStore.selectConversation(id)
}

function onNew() {
  chatStore.newConversation()
}

function onDelete(id: string, event: Event) {
  event.stopPropagation()
  chatStore.removeConversation(id)
}
</script>

<template>
  <div class="conversation-list">
    <div class="list-header">
      <span>对话历史</span>
      <n-button size="small" type="primary" @click="onNew">+ 新建</n-button>
    </div>
    <div class="list-body">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.id"
        class="conv-item"
        :class="{ active: conv.id === chatStore.activeConversationId }"
        @click="onSelect(conv.id)"
      >
        <div class="conv-info">
          <div class="conv-title">{{ conv.title || '新对话' }}</div>
          <div class="conv-meta">
            {{ conv.database }} · {{ conv.message_count }} 条消息
          </div>
        </div>
        <n-popconfirm @positive-click="onDelete(conv.id, $event)">
          <template #trigger>
            <n-button size="tiny" text type="error">✕</n-button>
          </template>
          确定删除此对话？
        </n-popconfirm>
      </div>
      <div v-if="chatStore.conversations.length === 0" class="empty-hint">
        暂无对话，点击"+ 新建"开始
      </div>
    </div>
  </div>
</template>

<style scoped>
.conversation-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e8eaed;
  background: #fafbfc;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8eaed;
  font-weight: 600;
}
.list-body {
  flex: 1;
  overflow-y: auto;
}
.conv-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.15s;
}
.conv-item:hover { background: #e8f0fe; }
.conv-item.active { background: #d6e4ff; }
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}
.empty-hint {
  padding: 24px;
  text-align: center;
  color: #999;
  font-size: 13px;
}
</style>
