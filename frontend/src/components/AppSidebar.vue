<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{
  active: 'overview' | 'stocks' | 'progress' | 'quant'
}>()

const router = useRouter()
const flowerUrl = import.meta.env.VITE_FLOWER_URL ?? 'http://127.0.0.1:5555'

function goOverview() {
  router.push('/')
}

function goStocks() {
  router.push('/stocks')
}

function goQuant() {
  router.push('/quant')
}

function goProgress() {
  router.push('/progress')
}

function openFlowerTab() {
  window.open(flowerUrl, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <aside class="sidebar card">
    <div class="sidebar-block">
      <h2>系统导航</h2>
    </div>

    <nav class="sidebar-nav">
      <button type="button" class="sidebar-link" :class="{ active: active === 'overview' }" @click="goOverview">
        首页总览
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'stocks' }" @click="goStocks">
        个股行情
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'quant' }" @click="goQuant">
        量化展示
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'progress' }" @click="goProgress">
        开发进度
      </button>
      <button type="button" class="sidebar-link" @click="openFlowerTab">任务监控（Flower）</button>
    </nav>
  </aside>
</template>
