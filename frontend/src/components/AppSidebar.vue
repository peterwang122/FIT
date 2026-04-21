<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{
  active: 'overview' | 'stocks' | 'markets' | 'progress' | 'quant' | 'account' | 'tasks'
}>()

const router = useRouter()

function goOverview() {
  void router.push('/')
}

function goStocks() {
  void router.push('/stocks')
}

function goMarkets() {
  void router.push('/markets')
}

function goQuant() {
  void router.push('/quant/index')
}

function goTasks() {
  void router.push('/tasks/manage')
}

function goProgress() {
  void router.push('/progress')
}

function goAccount() {
  void router.push('/account')
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
      <button type="button" class="sidebar-link" :class="{ active: active === 'markets' }" @click="goMarkets">
        港/美股
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'quant' }" @click="goQuant">
        量化分析
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'tasks' }" @click="goTasks">
        任务中心
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'progress' }" @click="goProgress">
        开发进度
      </button>
      <button type="button" class="sidebar-link" :class="{ active: active === 'account' }" @click="goAccount">
        个人中心
      </button>
    </nav>
  </aside>
</template>
