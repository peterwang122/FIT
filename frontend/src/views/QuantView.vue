<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'

const route = useRoute()

const tabs = [
  { key: 'index', label: '指数', to: '/quant/index' },
  { key: 'stock', label: '股票', to: '/quant/stock' },
  { key: 'strategies', label: '策略存储和收益曲线', to: '/quant/strategies' },
]

const activeTab = computed(() => {
  if (route.path.startsWith('/quant/stock')) return 'stock'
  if (route.path.startsWith('/quant/strategies')) return 'strategies'
  return 'index'
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="quant" />

    <main class="dashboard-main quant-main">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h2>量化展示</h2>
            <p class="muted">按指数、股票和策略存储三个子模块组织量化数据与信号。</p>
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
