<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  send: [message: string]
}>()

const input = ref('')
const isLoading = defineProps<{ loading: boolean }>()

function onSend() {
  const msg = input.value.trim()
  if (!msg || isLoading.loading) return
  emit('send', msg)
  input.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}
</script>

<template>
  <div class="chat-input">
    <n-input
      v-model:value="input"
      type="textarea"
      placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
      :autosize="{ minRows: 1, maxRows: 4 }"
      :disabled="loading"
      @keydown="onKeydown"
    />
    <n-button
      type="primary"
      :loading="loading"
      :disabled="!input.trim()"
      @click="onSend"
    >
      发送
    </n-button>
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid #e8eaed;
  background: #fff;
  align-items: flex-end;
}
.chat-input :deep(.n-input) {
  flex: 1;
}
</style>
