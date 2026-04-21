<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { fetchIndexKline, fetchIndexOptions } from '../api/stocks'
import AppSidebar from '../components/AppSidebar.vue'
import KlineChart from '../components/KlineChart.vue'
import type { QuantTargetMarket } from '../types/quant'
import type { KlineCandle, MarketOption } from '../types/stock'

const DEFAULT_INDEX_CODES: Record<Extract<QuantTargetMarket, 'hk' | 'us'>, string> = {
  hk: 'HSI',
  us: '.INX',
}

const DEFAULT_INDEX_NAMES: Record<Extract<QuantTargetMarket, 'hk' | 'us'>, string> = {
  hk: '恒生指数',
  us: '标普500指数',
}

const market = ref<Extract<QuantTargetMarket, 'hk' | 'us'>>('hk')
const marketOptions = [
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
] as const

const indexOptions = ref<MarketOption[]>([])
const indexCode = ref('')
const candles = ref<KlineCandle[]>([])
const loading = ref(false)
const error = ref('')

const selectedIndexName = computed(() => indexOptions.value.find((item) => item.code === indexCode.value)?.name ?? '')
const latestSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : null))

function getErrorMessage(errorValue: unknown) {
  return errorValue instanceof Error ? errorValue.message : '行情加载失败'
}

function resolveDefaultIndexCode(options: MarketOption[], nextMarket: Extract<QuantTargetMarket, 'hk' | 'us'>) {
  const preferredCode = DEFAULT_INDEX_CODES[nextMarket]
  if (options.some((item) => item.code === preferredCode)) {
    return preferredCode
  }
  const preferredName = DEFAULT_INDEX_NAMES[nextMarket]
  return options.find((item) => item.name === preferredName)?.code ?? options[0]?.code ?? ''
}

async function loadIndexOptions(preferredCode?: string) {
  const options = await fetchIndexOptions(market.value)
  indexOptions.value = options
  if (preferredCode && options.some((item) => item.code === preferredCode)) {
    indexCode.value = preferredCode
    return
  }
  indexCode.value = resolveDefaultIndexCode(options, market.value)
}

async function loadKline() {
  if (!indexCode.value) {
    candles.value = []
    error.value = '当前市场暂无可展示的指数'
    return
  }
  loading.value = true
  error.value = ''
  try {
    candles.value = await fetchIndexKline(indexCode.value, undefined, undefined, market.value)
    if (!candles.value.length) {
      error.value = `${selectedIndexName.value || indexCode.value} 暂无行情数据`
    }
  } catch (loadError) {
    candles.value = []
    error.value = getErrorMessage(loadError)
  } finally {
    loading.value = false
  }
}

async function initialize(preferredCode?: string) {
  loading.value = true
  error.value = ''
  try {
    await loadIndexOptions(preferredCode)
    await loadKline()
  } catch (loadError) {
    indexOptions.value = []
    indexCode.value = ''
    candles.value = []
    error.value = getErrorMessage(loadError)
    loading.value = false
  }
}

onMounted(async () => {
  await initialize()
})

watch(market, async () => {
  await initialize()
})

watch(indexCode, async (nextCode, previousCode) => {
  if (!nextCode || nextCode === previousCode) return
  await loadKline()
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="markets" />

    <main class="dashboard-main">
      <p v-if="error" class="banner-error">{{ error }}</p>

      <section class="stock-stage">
        <div class="section-head">
          <div>
            <h2>港/美股</h2>
            <p class="muted">这里只展示港股和美股指数行情，不包含量化图表、策略编辑和回测能力。</p>
          </div>
        </div>

        <div class="stock-stage-grid">
          <aside class="card stock-control-panel">
            <div class="stock-control-block">
              <h3>市场切换</h3>
              <div class="quant-subnav">
                <button
                  v-for="item in marketOptions"
                  :key="item.value"
                  type="button"
                  class="quant-subnav-link"
                  :class="{ active: market === item.value }"
                  @click="market = item.value"
                >
                  {{ item.label }}
                </button>
              </div>
            </div>

            <div class="stock-control-block">
              <h3>指数选择</h3>
              <select v-model="indexCode" class="input" :disabled="loading || !indexOptions.length">
                <option v-for="item in indexOptions" :key="item.code" :value="item.code">
                  {{ item.name }}
                </option>
              </select>
            </div>
          </aside>

          <div class="stock-content">
            <section v-if="latestSnapshot" class="card summary stock-summary">
              <div class="symbol-head">{{ selectedIndexName || '未命名指数' }}（{{ indexCode }}）</div>
              <div>
                <div class="label">交易日期</div>
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
                <div class="label">成交额</div>
                <div class="value">{{ latestSnapshot.amount }}</div>
              </div>
            </section>

            <section class="card stock-chart-panel stock-chart-panel-tall">
              <div class="panel-head">
                <div>
                  <h2>指数 K 线</h2>
                  <p class="muted">当前市场：{{ market === 'hk' ? '港股' : '美股' }}</p>
                </div>
              </div>

              <KlineChart :candles="candles" :symbol-name="selectedIndexName" :symbol-code="indexCode" :height="920" />
            </section>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
