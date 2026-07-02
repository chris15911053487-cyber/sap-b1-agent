<script setup lang="ts">
import LayoutHeader from './components/LayoutHeader.vue'
</script>

<template>
  <n-config-provider :locale="null" :theme="null">
    <n-layout>
      <LayoutHeader />
      <n-layout-content>
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-config-provider>
</template>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
#app { height: 100vh; }
</style>
