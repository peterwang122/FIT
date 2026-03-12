<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import KlineChart from '../components/KlineChart.vue'
import { useStockStore } from '../stores/stock'

const stockStore = useStockStore()
const { tsCode, symbols, candles, loading, collectTaskId, collectState, meta, error } = storeToRefs(stockStore)

const activeTab = ref<'market' | 'monitor'>('market')
const flowerUrl = import.meta.env.VITE_FLOWER_URL ?? 'http://127.0.0.1:5555'

const latestSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))

onMounted(async () => {
  await stockStore.initialize()
})
</script>

<template>
  <div class="page-wrap">
    <div class="tab-bar card">
      <button class="tab-btn" :class="{ active: activeTab === 'market' }" @click="activeTab = 'market'">行情中心</button>
      <button class="tab-btn" :class="{ active: activeTab === 'monitor' }" @click="activeTab = 'monitor'">任务监控（Flower）</button>
    </div>

    <section v-if="activeTab === 'market'" class="market-grid">
      <aside class="card panel-left">
        <h3>股票选择</h3>
        <select v-model="tsCode" class="input" @change="stockStore.loadKline">
          <option value="" disabled>请选择股票代码</option>
          <option v-for="item in symbols" :key="item.ts_code" :value="item.ts_code">{{ item.ts_code }}</option>
        </select>

        <div class="btn-group">
          <button @click="stockStore.loadKline" :disabled="loading" class="btn primary">刷新K线</button>
          <button @click="stockStore.triggerCollect" :disabled="!tsCode" class="btn">触发采集</button>
          <button @click="stockStore.refreshTaskStatus" :disabled="!collectTaskId" class="btn">刷新任务状态</button>
        </div>

        <p class="muted">任务ID：{{ collectTaskId || '-' }}</p>
        <p class="muted">状态：{{ collectState || '-' }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </aside>

      <main>
        <section class="card summary" v-if="latestSnapshot">
          <div>
            <div class="label">交易日</div>
            <div class="value">{{ latestSnapshot.trade_date }}</div>
          </div>
          <div>
            <div class="label">收盘价</div>
            <div class="value">{{ latestSnapshot.close }}</div>
          </div>
          <div>
            <div class="label">涨跌幅</div>
            <div class="value">{{ latestSnapshot.pct_chg }}%</div>
          </div>
          <div>
            <div class="label">成交量</div>
            <div class="value">{{ latestSnapshot.vol }}</div>
          </div>
        </section>

        <KlineChart :candles="candles" />

        <section class="card meta" v-if="meta">
          <h3>数据库字段映射（只读）</h3>
          <p class="muted">数据表：{{ meta.table_name }}</p>
          <div class="meta-grid">
            <div v-for="(value, key) in meta.column_mapping" :key="key" class="meta-item">
              <span>{{ key }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
        </section>
      </main>
    </section>

    <section v-else class="card flower-card">
      <h2>Flower 任务监控</h2>
      <p class="muted">点击按钮跳转到 Flower 管理页面，查看任务状态、失败重试与队列情况。</p>
      <a :href="flowerUrl" target="_blank" rel="noreferrer" class="btn primary">打开 Flower</a>
    </section>
  </div>
</template>
