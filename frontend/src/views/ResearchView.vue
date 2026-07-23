<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="research" />

    <main class="dashboard-main quant-main">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h2>研究成果</h2>
            <p class="muted">量化研究、历史事件检验与可执行参数对照。</p>
          </div>
        </div>

        <nav class="quant-subnav">
          <RouterLink to="/research/vix-options" class="quant-subnav-link" active-class="active">
            VIX底部期权
          </RouterLink>
          <RouterLink to="/research/csi1000-futures" class="quant-subnav-link" active-class="active">
            中证1000期货
          </RouterLink>
        </nav>
      </section>

      <RouterView />
    </main>
  </div>
</template>
