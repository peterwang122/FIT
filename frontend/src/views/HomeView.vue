<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import KlineChart from '../components/KlineChart.vue'
import { useStockStore } from '../stores/stock'

const stockStore = useStockStore()
const { tsCode, searchKeyword, symbols, candles, loading, collectTaskId, collectState, meta, dbStatus, error } =
  storeToRefs(stockStore)

const activeTab = ref<'market' | 'monitor'>('market')
const flowerUrl = import.meta.env.VITE_FLOWER_URL ?? 'http://127.0.0.1:5555'
const showSuggestions = ref(false)

const latestSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))
const selectedName = computed(() => stockStore.selectedSymbolName)

const filteredSymbols = computed(() => {
  const key = searchKeyword.value.trim().toLowerCase()
  if (!key) return symbols.value.slice(0, 30)
  return symbols.value
    .filter((item) => item.ts_code.toLowerCase().includes(key) || item.stock_name.toLowerCase().includes(key))
    .slice(0, 30)
})

function openFlowerTab() {
  activeTab.value = 'monitor'
  window.open(flowerUrl, '_blank', 'noopener,noreferrer')
}

async function pickSymbol(code: string, name: string) {
  tsCode.value = code
  searchKeyword.value = `${code} ${name}`
  showSuggestions.value = false
  await stockStore.loadKline()
}

onMounted(async () => {
  await stockStore.initialize()
  if (selectedName.value) {
    searchKeyword.value = `${tsCode.value} ${selectedName.value}`
  }
})
</script>

<template>
  <div class="page-wrap">
    <div class="tab-bar card">
      <button class="tab-btn" :class="{ active: activeTab === 'market' }" @click="activeTab = 'market'">行情中心</button>
      <button class="tab-btn" :class="{ active: activeTab === 'monitor' }" @click="openFlowerTab">任务监控（Flower）</button>
    </div>

    <section v-if="activeTab === 'market'" class="market-grid">
      <aside class="card panel-left">
        <h3>股票选择</h3>

        <div class="db-check" v-if="dbStatus">
          <div class="db-row">
            <span>数据库连接</span>
            <strong :class="dbStatus.connected ? 'ok' : 'bad'">{{ dbStatus.connected ? '已连接' : '未连接' }}</strong>
          </div>
          <div class="db-row">
            <span>总记录</span>
            <strong>{{ dbStatus.row_count }}</strong>
          </div>
          <div class="db-row">
            <span>股票数量</span>
            <strong>{{ dbStatus.symbol_count }}</strong>
          </div>
          <button class="btn" @click="stockStore.refreshDbStatus">刷新连接状态</button>
        </div>

        <div class="search-wrap">
          <input
            v-model="searchKeyword"
            class="input"
            placeholder="输入股票代码或股票名称"
            @focus="showSuggestions = true"
            @input="showSuggestions = true"
          />
          <ul v-if="showSuggestions" class="suggest-list">
            <li v-for="item in filteredSymbols" :key="item.ts_code" @mousedown.prevent="pickSymbol(item.ts_code, item.stock_name)">
              <span>{{ item.ts_code }}</span>
              <strong>{{ item.stock_name }}</strong>
            </li>
          </ul>
        </div>

        <div class="btn-group">
          <button @click="stockStore.loadKline" :disabled="loading" class="btn primary">刷新K线</button>
          <button @click="stockStore.triggerCollect" :disabled="!tsCode" class="btn">触发采集</button>
          <button @click="stockStore.refreshTaskStatus" :disabled="!collectTaskId" class="btn">刷新任务状态</button>
        </div>

        <p class="muted">当前代码：{{ tsCode || '-' }}</p>
        <p class="muted">任务ID：{{ collectTaskId || '-' }}</p>
        <p class="muted">状态：{{ collectState || '-' }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </aside>

      <main>
        <section class="card summary" v-if="latestSnapshot">
          <div class="symbol-head">{{ selectedName }} ({{ tsCode }})</div>
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
          <div>
            <div class="label">PE(TTM)</div>
            <div class="value small">{{ latestSnapshot.pe_ttm }}</div>
          </div>
          <div>
            <div class="label">PB</div>
            <div class="value small">{{ latestSnapshot.pb }}</div>
          </div>
          <div>
            <div class="label">总市值</div>
            <div class="value small">{{ latestSnapshot.total_market_value }}</div>
          </div>
          <div>
            <div class="label">流通市值</div>
            <div class="value small">{{ latestSnapshot.circulating_market_value }}</div>
          </div>
        </section>

        <KlineChart :candles="candles" :symbol-name="selectedName" :symbol-code="tsCode" />

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
