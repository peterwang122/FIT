<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'
import IndexEmotionChart from '../components/IndexEmotionChart.vue'
import KlineChart from '../components/KlineChart.vue'
import NetPositionLineChart from '../components/NetPositionLineChart.vue'
import NetPositionTable from '../components/NetPositionTable.vue'
import { useStockStore } from '../stores/stock'
import type { CffexSeriesKey } from '../types/stock'

const NET_POSITION_VIEW_OPTIONS = [
  { value: 'table', label: '表格' },
  { value: 'chart', label: '折线图' },
] as const

const NET_POSITION_SERIES_OPTIONS: { value: CffexSeriesKey; label: string }[] = [
  { value: 'OVERALL', label: '总体' },
  { value: 'IF', label: 'IF' },
  { value: 'IH', label: 'IH' },
  { value: 'IC', label: 'IC' },
  { value: 'IM', label: 'IM' },
]

const stockStore = useStockStore()
const route = useRoute()
const {
  tsCode,
  searchKeyword,
  netPositionDate,
  symbols,
  candles,
  indexEmotionPoints,
  netPositionTables,
  netPositionSeries,
  indexCode,
  indexOptions,
  indexCandles,
  forexCode,
  forexOptions,
  forexCandles,
  loading,
  indexLoading,
  forexLoading,
  netPositionSeriesLoading,
  collectTaskId,
  collectState,
  error,
  indexEmotionLoading,
  netPositionLoading,
} = storeToRefs(stockStore)

const showSuggestions = ref(false)
const netPositionDateInput = ref('')
const stockSectionRef = ref<HTMLElement | null>(null)
const netPositionViewMode = ref<'table' | 'chart'>('table')
const netPositionSeriesKey = ref<CffexSeriesKey>('OVERALL')

const latestStockSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))
const latestIndexSnapshot = computed(() =>
  indexCandles.value.length ? indexCandles.value[indexCandles.value.length - 1] : undefined,
)
const latestForexSnapshot = computed(() =>
  forexCandles.value.length ? forexCandles.value[forexCandles.value.length - 1] : undefined,
)
const selectedName = computed(() => stockStore.selectedSymbolName)
const selectedIndexName = computed(() => stockStore.selectedIndexName)
const selectedForexName = computed(() => stockStore.selectedForexName)
const citicNetPositionSeriesPoints = computed(
  () => netPositionSeries.value?.citic_customer?.series?.[netPositionSeriesKey.value] ?? [],
)
const top20NetPositionSeriesPoints = computed(
  () => netPositionSeries.value?.top20_institutions?.series?.[netPositionSeriesKey.value] ?? [],
)

const filteredSymbols = computed(() => {
  const key = searchKeyword.value.trim().toLowerCase()
  if (!key) return symbols.value.slice(0, 30)
  return symbols.value
    .filter((item) => item.ts_code.toLowerCase().includes(key) || item.stock_name.toLowerCase().includes(key))
    .slice(0, 30)
})

function scrollToStockSection() {
  stockSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function pickSymbol(code: string, name: string) {
  tsCode.value = code
  searchKeyword.value = `${code} ${name}`
  showSuggestions.value = false
  await stockStore.loadKline()
}

async function applyNetPositionDate(nextDate: string) {
  const result = await stockStore.loadNetPositionTables(nextDate || undefined)
  if (!result?.ok) {
    window.alert(result?.message ?? '所选日期暂无中金所净持仓数据')
    netPositionDateInput.value = netPositionDate.value || ''
    return
  }
  netPositionDateInput.value = stockStore.netPositionDate
}

async function resetNetPositionDate() {
  await applyNetPositionDate('')
}

async function syncHashScroll() {
  if (route.hash === '#stock-section') {
    await nextTick()
    scrollToStockSection()
  }
}

watch(netPositionDate, (value) => {
  netPositionDateInput.value = value || ''
})

watch(
  () => route.hash,
  async () => {
    await syncHashScroll()
  },
)

onMounted(async () => {
  await stockStore.initialize()
  if (selectedName.value) {
    searchKeyword.value = `${tsCode.value} ${selectedName.value}`
  }
  netPositionDateInput.value = netPositionDate.value || ''
  await syncHashScroll()
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="overview" @market="scrollToStockSection" />

    <main class="dashboard-main">
      <p v-if="error" class="banner-error">{{ error }}</p>

      <section class="hero-grid">
        <div class="hero-column hero-column-left">
          <section class="card hero-panel positions-panel">
            <div class="positions-toolbar">
              <div class="positions-toolbar-meta">
                <div v-if="netPositionTables?.citic_customer?.trade_date" class="panel-date">
                  数据日期 {{ netPositionTables.citic_customer.trade_date }}
                </div>

                <div class="positions-view-controls">
                  <select v-model="netPositionViewMode" class="input select">
                    <option v-for="item in NET_POSITION_VIEW_OPTIONS" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>

                  <select
                    v-if="netPositionViewMode === 'chart'"
                    v-model="netPositionSeriesKey"
                    class="input select"
                  >
                    <option v-for="item in NET_POSITION_SERIES_OPTIONS" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>
                </div>
              </div>

              <div class="positions-toolbar-controls">
                <label for="position-date" class="label-inline">日期</label>
                <input
                  id="position-date"
                  v-model="netPositionDateInput"
                  type="date"
                  class="input date-input"
                  :disabled="netPositionLoading"
                  @change="applyNetPositionDate(netPositionDateInput)"
                />
                <button class="btn" :disabled="netPositionLoading" @click="resetNetPositionDate">恢复最新</button>
              </div>
            </div>

            <div v-if="netPositionViewMode === 'table'" class="net-tables-stack">
              <NetPositionTable
                :table="netPositionTables?.citic_customer ?? null"
                :loading="netPositionLoading"
              />
              <NetPositionTable
                :table="netPositionTables?.top20_institutions ?? null"
                :loading="netPositionLoading"
              />
            </div>
            <div v-else class="net-tables-stack">
              <NetPositionLineChart
                title="中信期货(代客)净空单折线图"
                :points="citicNetPositionSeriesPoints"
                :loading="netPositionSeriesLoading"
                line-color="#dc2626"
              />
              <NetPositionLineChart
                title="前20机构净空单折线图"
                :points="top20NetPositionSeriesPoints"
                :loading="netPositionSeriesLoading"
                line-color="#2563eb"
              />
            </div>
          </section>

          <section class="card hero-panel chart-panel">
            <div class="compact-toolbar compact-toolbar-end">
              <select id="index-select" v-model="indexCode" class="input select" @change="stockStore.loadIndexKline">
                <option v-for="item in indexOptions" :key="item.code" :value="item.code">
                  {{ item.name }}
                </option>
              </select>
            </div>

            <section v-if="latestIndexSnapshot" class="summary summary-compact">
              <div class="symbol-head">{{ selectedIndexName }}（{{ indexCode }}）</div>
              <div>
                <div class="label">交易日期</div>
                <div class="value">{{ latestIndexSnapshot.trade_date }}</div>
              </div>
              <div>
                <div class="label">收盘价</div>
                <div class="value">{{ latestIndexSnapshot.close }}</div>
              </div>
              <div>
                <div class="label">涨跌幅</div>
                <div class="value">{{ latestIndexSnapshot.pct_chg }}%</div>
              </div>
              <div>
                <div class="label">成交量</div>
                <div class="value">{{ latestIndexSnapshot.vol }}</div>
              </div>
            </section>

            <p v-if="indexLoading" class="muted">指数 K 线加载中...</p>
            <KlineChart
              :candles="indexCandles"
              :symbol-name="selectedIndexName"
              :symbol-code="indexCode"
              :default-visible-days="30"
              height="100%"
            />
          </section>
        </div>

        <div class="hero-column hero-column-right">
          <IndexEmotionChart
            :points="indexEmotionPoints"
            :loading="indexEmotionLoading"
            :default-visible-days="30"
            height="100%"
          />

          <section class="card hero-panel chart-panel">
            <div class="compact-toolbar compact-toolbar-end">
              <select id="forex-select" v-model="forexCode" class="input select" @change="stockStore.loadForexKline">
                <option v-for="item in forexOptions" :key="item.code" :value="item.code">
                  {{ item.name }}
                </option>
              </select>
            </div>

            <section v-if="latestForexSnapshot" class="summary summary-compact">
              <div class="symbol-head">{{ selectedForexName }}（{{ forexCode }}）</div>
              <div>
                <div class="label">交易日期</div>
                <div class="value">{{ latestForexSnapshot.trade_date }}</div>
              </div>
              <div>
                <div class="label">最新价</div>
                <div class="value">{{ latestForexSnapshot.close }}</div>
              </div>
              <div>
                <div class="label">最高价</div>
                <div class="value">{{ latestForexSnapshot.high }}</div>
              </div>
              <div>
                <div class="label">最低价</div>
                <div class="value">{{ latestForexSnapshot.low }}</div>
              </div>
            </section>

            <p v-if="forexLoading" class="muted">汇率 K 线加载中...</p>
            <KlineChart
              :candles="forexCandles"
              :symbol-name="selectedForexName"
              :symbol-code="forexCode"
              :default-visible-days="30"
              height="100%"
            />
          </section>
        </div>
      </section>

      <section id="stock-section" ref="stockSectionRef" class="stock-stage">
        <div class="section-head">
          <div>
            <h2>行情中心</h2>
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
                  <h2>股票 K 线</h2>
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
