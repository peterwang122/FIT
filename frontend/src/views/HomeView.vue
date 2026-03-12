<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted } from 'vue'

import KlineChart from '../components/KlineChart.vue'
import { useStockStore } from '../stores/stock'

const stockStore = useStockStore()
const { tsCode, candles, loading, collectTaskId, collectState } = storeToRefs(stockStore)

const latestSnapshot = computed(() => candles.value.at(-1))

onMounted(async () => {
  await stockStore.loadKline()
})
</script>

<template>
  <section class="card" style="margin-bottom: 12px">
    <h2>数据采集任务（Celery）</h2>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom: 8px">
      <label>
        股票代码：
        <input v-model="tsCode" />
      </label>
      <button @click="stockStore.loadKline" :disabled="loading">刷新K线</button>
      <button @click="stockStore.triggerCollect">触发采集</button>
      <button @click="stockStore.refreshTaskStatus" :disabled="!collectTaskId">刷新任务状态</button>
    </div>
    <p>任务ID：{{ collectTaskId || '-' }}，状态：{{ collectState || '-' }}</p>
    <p v-if="latestSnapshot">
      最新：{{ latestSnapshot.trade_date }} 收盘 {{ latestSnapshot.close }} / 涨跌幅 {{ latestSnapshot.pct_chg }}%
    </p>
  </section>

  <KlineChart :candles="candles" />
</template>
