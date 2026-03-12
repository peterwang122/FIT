<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import KlineTable from '../components/KlineTable.vue'
import { useStockStore } from '../stores/stock'

const stockStore = useStockStore()
const { tsCode, candles, loading, collectTaskId, collectState } = storeToRefs(stockStore)

onMounted(async () => {
  await stockStore.loadKline()
})
</script>

<template>
  <section class="card" style="margin-bottom: 12px">
    <h2>数据采集任务（Celery）</h2>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
      <label>
        股票代码：
        <input v-model="tsCode" />
      </label>
      <button @click="stockStore.loadKline" :disabled="loading">刷新K线</button>
      <button @click="stockStore.triggerCollect">触发采集</button>
      <button @click="stockStore.refreshTaskStatus" :disabled="!collectTaskId">刷新任务状态</button>
    </div>
    <p style="margin-top:8px">任务ID：{{ collectTaskId || '-' }}，状态：{{ collectState || '-' }}</p>
  </section>

  <KlineTable :candles="candles" />
</template>
