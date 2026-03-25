<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import AppSidebar from '../components/AppSidebar.vue'
import KlineChart from '../components/KlineChart.vue'
import { useStockStore } from '../stores/stock'

const stockStore = useStockStore()
const { tsCode, searchKeyword, symbols, candles, loading, collectTaskId, collectState, error } = storeToRefs(stockStore)

const showSuggestions = ref(false)

const latestStockSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))
const selectedName = computed(() => stockStore.selectedSymbolName)

const filteredSymbols = computed(() => {
  const key = searchKeyword.value.trim().toLowerCase()
  if (!key) return symbols.value.slice(0, 30)
  return symbols.value
    .filter((item) => item.ts_code.toLowerCase().includes(key) || item.stock_name.toLowerCase().includes(key))
    .slice(0, 30)
})

async function pickSymbol(code: string, name: string) {
  tsCode.value = code
  searchKeyword.value = `${code} ${name}`
  showSuggestions.value = false
  await stockStore.loadKline()
}

onMounted(async () => {
  await stockStore.initializeStocksPage()
  if (selectedName.value) {
    searchKeyword.value = `${tsCode.value} ${selectedName.value}`
  }
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="stocks" />

    <main class="dashboard-main">
      <p v-if="error" class="banner-error">{{ error }}</p>

      <section class="stock-stage">
        <div class="section-head">
          <div>
            <h2>个股行情</h2>
          </div>
        </div>

        <div class="stock-stage-grid">
          <aside class="card stock-control-panel">
            <div class="stock-control-block">
              <h3>股票搜索</h3>
              <div class="search-wrap">
                <input
                  v-model="searchKeyword"
                  class="input"
                  placeholder="输入股票代码或股票名称"
                  @focus="showSuggestions = true"
                  @input="showSuggestions = true"
                />
                <ul v-if="showSuggestions" class="suggest-list">
                  <li
                    v-for="item in filteredSymbols"
                    :key="item.ts_code"
                    @mousedown.prevent="pickSymbol(item.ts_code, item.stock_name)"
                  >
                    <span>{{ item.ts_code }}</span>
                    <strong>{{ item.stock_name }}</strong>
                  </li>
                </ul>
              </div>
            </div>

            <div class="btn-group">
              <button @click="stockStore.loadKline" :disabled="loading" class="btn primary">刷新股票 K 线</button>
              <button @click="stockStore.triggerCollect" :disabled="!tsCode" class="btn">触发采集</button>
              <button @click="stockStore.refreshTaskStatus" :disabled="!collectTaskId" class="btn">刷新任务状态</button>
            </div>

            <div class="stock-status-list">
              <div class="stock-status-item">
                <span>当前股票</span>
                <strong>{{ selectedName || '-' }}（{{ tsCode || '-' }}）</strong>
              </div>
              <div class="stock-status-item">
                <span>任务 ID</span>
                <strong>{{ collectTaskId || '-' }}</strong>
              </div>
              <div class="stock-status-item">
                <span>任务状态</span>
                <strong>{{ collectState || '-' }}</strong>
              </div>
            </div>
          </aside>

          <div class="stock-content">
            <section v-if="latestStockSnapshot" class="card summary stock-summary">
              <div class="symbol-head">{{ selectedName }}（{{ tsCode }}）</div>
              <div>
                <div class="label">交易日期</div>
                <div class="value">{{ latestStockSnapshot.trade_date }}</div>
              </div>
              <div>
                <div class="label">收盘价</div>
                <div class="value">{{ latestStockSnapshot.close }}</div>
              </div>
              <div>
                <div class="label">涨跌幅</div>
                <div class="value">{{ latestStockSnapshot.pct_chg }}%</div>
              </div>
              <div>
                <div class="label">成交量</div>
                <div class="value">{{ latestStockSnapshot.vol }}</div>
              </div>
              <div>
                <div class="label">PE(TTM)</div>
                <div class="value small">{{ latestStockSnapshot.pe_ttm }}</div>
              </div>
              <div>
                <div class="label">PB</div>
                <div class="value small">{{ latestStockSnapshot.pb }}</div>
              </div>
              <div>
                <div class="label">总市值</div>
                <div class="value small">{{ latestStockSnapshot.total_market_value }}</div>
              </div>
              <div>
                <div class="label">流通市值</div>
                <div class="value small">{{ latestStockSnapshot.circulating_market_value }}</div>
              </div>
            </section>

            <section class="card stock-chart-panel stock-chart-panel-tall">
              <div class="panel-head">
                <div>
                  <h2>个股 K 线</h2>
                </div>
              </div>

              <KlineChart :candles="candles" :symbol-name="selectedName" :symbol-code="tsCode" :height="920" />
            </section>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
