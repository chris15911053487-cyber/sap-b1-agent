<script setup lang="ts">
defineProps<{ intent: string }>()

const intentLabels: Record<string, string> = {
  query: '查询',
  build_sp: '构建SP',
  verify: '校验',
  chat: '对话',
}

const intentColors: Record<string, string> = {
  query: '#2080f0',
  build_sp: '#f0a020',
  verify: '#18a058',
  chat: '#909399',
}
</script>

<template>
  <n-tag
    :color="{ color: intentColors[intent] || '#909399', textColor: '#fff' }"
    size="small"
    round
  >
    {{ intentLabels[intent] || intent }}
  </n-tag>
</template>
