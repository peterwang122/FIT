<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchSymbols } from '../api/stocks'
import AppSidebar from '../components/AppSidebar.vue'
import KlineChart from '../components/KlineChart.vue'
import { useStockStore } from '../stores/stock'
import type { StockSymbol } from '../types/stock'

const stockStore = useStockStore()
const { tsCode, searchKeyword, candles, loading, error } = storeToRefs(stockStore)

const showSuggestions = ref(false)
const suggestionLoading = ref(false)
const suggestions = ref<StockSymbol[]>([])
const selectedStockName = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null
let latestSearchRequestId = 0

const latestStockSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))
const selectedName = computed(() => selectedStockName.value)

async function loadSuggestions(keyword: string) {
  const requestId = ++latestSearchRequestId
  suggestionLoading.value = true
  try {
    const items = await fetchSymbols(30, keyword)
    if (requestId !== latestSearchRequestId) {
      return
    }
    suggestions.value = items
  } finally {
    if (requestId === latestSearchRequestId) {
      suggestionLoading.value = false
    }
  }
}

function scheduleSuggestionSearch(keyword: string) {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    void loadSuggestions(keyword)
  }, 280)
}

function handleSearchFocus() {
  showSuggestions.value = true
  scheduleSuggestionSearch(searchKeyword.value.trim())
}

function handleSearchInput() {
  showSuggestions.value = true
  scheduleSuggestionSearch(searchKeyword.value.trim())
}

async function hydrateSelectedStockName() {
  if (!tsCode.value) return
  try {
    const items = await fetchSymbols(10, tsCode.value)
    const matched = items.find((item) => item.ts_code === tsCode.value)
    if (matched) {
      selectedStockName.value = matched.stock_name
      searchKeyword.value = `${matched.ts_code} ${matched.stock_name}`
    } else {
      searchKeyword.value = tsCode.value
    }
  } catch {
    searchKeyword.value = tsCode.value
  }
}

async function pickSymbol(code: string, name: string) {
  tsCode.value = code
  selectedStockName.value = name
  searchKeyword.value = `${code} ${name}`
  showSuggestions.value = false
  suggestions.value = []
  await stockStore.loadKline()
}

onMounted(async () => {
  await stockStore.initializeStocksPage()
  await hydrateSelectedStockName()
})

onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
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
                  @focus="handleSearchFocus"
                  @input="handleSearchInput"
                />
                <ul v-if="showSuggestions" class="suggest-list">
                  <li v-if="suggestionLoading">
                    <span>搜索中...</span>
                  </li>
                  <li v-else-if="!suggestions.length">
                    <span>没有匹配结果</span>
                  </li>
                  <template v-else>
                    <li
                      v-for="item in suggestions"
                      :key="item.ts_code"
                      @mousedown.prevent="pickSymbol(item.ts_code, item.stock_name)"
                    >
                      <span>{{ item.ts_code }}</span>
                      <strong>{{ item.stock_name }}</strong>
                    </li>
                  </template>
                </ul>
              </div>
            </div>
          </aside>

          <div class="stock-content">
            <section v-if="latestStockSnapshot" class="card summary stock-summary">
              <div class="symbol-head">{{ selectedName || '未命名股票' }}（{{ tsCode }}）</div>
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
