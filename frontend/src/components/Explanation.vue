<script setup lang="ts">
import { marked } from 'marked'

const props = defineProps<{ text: string }>()

const rendered = marked.parse(props.text || '')
</script>

<template>
  <div class="explanation" v-html="rendered"></div>
</template>

<style scoped>
.explanation {
  line-height: 1.7;
  font-size: 14px;
}
.explanation :deep(p) { margin: 4px 0; }
.explanation :deep(strong) { color: #333; }
</style>
