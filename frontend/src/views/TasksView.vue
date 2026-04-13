<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const tabs = computed(() => {
  const base = [{ key: 'manage', label: '任务管理', to: '/tasks/manage' }]
  if (authStore.isRoot) {
    base.push({ key: 'strategies', label: '全部策略', to: '/tasks/strategies' })
    base.push({ key: 'monitor', label: '任务监控', to: '/tasks/monitor' })
  }
  return base
})

const activeTab = computed(() => {
  if (route.path.startsWith('/tasks/monitor')) return 'monitor'
  if (route.path.startsWith('/tasks/strategies')) return 'strategies'
  return 'manage'
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="tasks" />

    <main class="dashboard-main tasks-main">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h2>任务中心</h2>
            <p class="muted">在这里统一管理定时采集、定时通知，以及 root 专属的策略浏览与任务监控。</p>
          </div>
        </div>

        <nav class="quant-subnav">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.key"
            :to="tab.to"
            class="quant-subnav-link"
            :class="{ active: activeTab === tab.key }"
          >
            {{ tab.label }}
          </RouterLink>
        </nav>
      </section>

      <RouterView />
    </main>
  </div>
</template>
