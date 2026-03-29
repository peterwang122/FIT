<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

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
const {
  netPositionDate,
  indexEmotionPoints,
  netPositionTables,
  netPositionSeries,
  indexCode,
  indexOptions,
  indexCandles,
  forexCode,
  forexOptions,
  forexCandles,
  indexLoading,
  forexLoading,
  netPositionSeriesLoading,
  error,
  indexEmotionLoading,
  netPositionLoading,
} = storeToRefs(stockStore)

const netPositionDateInput = ref('')
const netPositionViewMode = ref<'table' | 'chart'>('table')
const netPositionSeriesKey = ref<CffexSeriesKey>('OVERALL')

const latestIndexSnapshot = computed(() =>
  indexCandles.value.length ? indexCandles.value[indexCandles.value.length - 1] : undefined,
)
const latestForexSnapshot = computed(() =>
  forexCandles.value.length ? forexCandles.value[forexCandles.value.length - 1] : undefined,
)
const selectedIndexName = computed(() => stockStore.selectedIndexName)
const selectedForexName = computed(() => stockStore.selectedForexName)
const citicNetPositionSeriesPoints = computed(
  () => netPositionSeries.value?.citic_customer?.series?.[netPositionSeriesKey.value] ?? [],
)
const top20NetPositionSeriesPoints = computed(
  () => netPositionSeries.value?.top20_institutions?.series?.[netPositionSeriesKey.value] ?? [],
)

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

watch(netPositionDate, (value) => {
  netPositionDateInput.value = value || ''
})

onMounted(async () => {
  await stockStore.initializeOverview()
  netPositionDateInput.value = netPositionDate.value || ''
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="overview" />

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
              <NetPositionTable :table="netPositionTables?.citic_customer ?? null" :loading="netPositionLoading" />
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
              :default-visible-days="120"
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
              :default-visible-days="90"
              height="100%"
            />
          </section>
        </div>
      </section>
    </main>
  </div>
</template>
