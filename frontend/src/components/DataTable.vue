<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ markdown: string }>()

// Parse simple markdown table into structured data
const tableData = computed(() => {
  if (!props.markdown) return null
  const lines = props.markdown.trim().split('\n')
  if (lines.length < 2) return null

  // Parse header
  const headers = lines[0]
    .split('|')
    .map(h => h.trim())
    .filter(Boolean)

  // Skip separator line (line[1])
  // Parse data rows (skip last line if it starts with _)
  const rows = lines.slice(2)
    .filter(line => !line.startsWith('_'))
    .map(line =>
      line
        .split('|')
        .map(c => c.trim())
        .filter(Boolean)
    )

  return { headers, rows }
})
</script>

<template>
  <div v-if="tableData" class="data-table">
    <n-data-table
      :columns="tableData.headers.map((h, i) => ({ title: h, key: String(i) }))"
      :data="tableData.rows.map((row, ri) => {
        const obj: Record<string, string> = { key: String(ri) }
        row.forEach((cell, ci) => { obj[String(ci)] = cell })
        return obj
      })"
      :max-height="400"
      :single-line="false"
      size="small"
      striped
    />
  </div>
  <div v-else-if="markdown" class="raw-markdown" v-text="markdown"></div>
</template>

<style scoped>
.data-table {
  margin: 8px 0;
}
.raw-markdown {
  padding: 12px;
  color: #999;
  font-style: italic;
}
</style>
