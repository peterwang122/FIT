<script setup lang="ts">
import { computed } from 'vue'

import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const flowerProxyUrl = computed(() => `${apiBase}/tasks/monitor/flower/`)
</script>

<template>
  <section class="card task-monitor-card">
    <div class="progress-section-head">
      <div class="progress-section-copy">
        <h3>任务监控（Flower）</h3>
        <p class="muted">这里展示的是全局 Celery 运行态，因此仅 root 用户可见。</p>
      </div>
    </div>

    <template v-if="authStore.isRoot">
      <iframe class="task-monitor-frame" :src="flowerProxyUrl" title="Flower Monitor"></iframe>
    </template>
    <template v-else>
      <div class="quant-stock-empty">
        <h3>无访问权限</h3>
        <p class="muted">任务监控仅对 root 用户开放。你仍然可以在“任务管理”里查看和维护自己名下的任务。</p>
      </div>
    </template>
  </section>
</template>
