<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <div class="brand-lockup">
        <img src="/logo1-header.png" alt="FIT logo" class="brand-logo" />
        <div class="brand-copy">
          <h1>FIT 股票量化系统</h1>
          <p class="brand-subtitle">Fixed Immortal Travel Stock Quantitative Platform</p>
        </div>
      </div>
    </header>

    <RouterView />
  </div>
</template>
