<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="risk" />

    <main class="dashboard-main quant-main">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h2>风险监控</h2>
            <p class="muted">追踪风险状态、证据变化和历史调整，不产生买卖信号。</p>
          </div>
        </div>

        <nav class="quant-subnav">
          <RouterLink to="/risk/csi1000" class="quant-subnav-link" active-class="active">
            中证1000
          </RouterLink>
        </nav>
      </section>

      <RouterView />
    </main>
  </div>
</template>
