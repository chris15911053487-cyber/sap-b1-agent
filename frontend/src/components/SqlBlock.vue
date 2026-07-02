<script setup lang="ts">
import { ref } from 'vue'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('sql', sql)

const props = defineProps<{ sql: string }>()

const highlighted = hljs.highlight(props.sql, { language: 'sql' }).value

const copied = ref(false)
function copySql() {
  navigator.clipboard.writeText(props.sql)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}
</script>

<template>
  <div class="sql-block">
    <div class="sql-header">
      <span class="sql-label">SQL</span>
      <n-button size="tiny" text @click="copySql">
        {{ copied ? '已复制' : '复制' }}
      </n-button>
    </div>
    <pre><code class="language-sql" v-html="highlighted"></code></pre>
  </div>
</template>

<style scoped>
.sql-block {
  background: #f6f8fa;
  border-radius: 6px;
  overflow: hidden;
  margin: 8px 0;
}
.sql-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #e8eaed;
  font-size: 12px;
}
.sql-label {
  font-weight: 600;
  color: #666;
}
pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
}
</style>
