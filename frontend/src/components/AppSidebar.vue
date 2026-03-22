<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{
  active: 'overview' | 'progress' | 'quant'
}>()

const emit = defineEmits<{
  market: []
}>()

const router = useRouter()
const flowerUrl = import.meta.env.VITE_FLOWER_URL ?? 'http://127.0.0.1:5555'

function goOverview() {
  router.push('/')
}

function goMarket() {
  if (props.active === 'overview') {
    emit('market')
    return
  }
  router.push({ path: '/', hash: '#stock-section' })
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
      <button type="button" class="sidebar-link" @click="goMarket">行情中心</button>
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
