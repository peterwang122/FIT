<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { fetchVixOptionContractKline } from '../api/research'
import OptionContractKlineChart from './OptionContractKlineChart.vue'
import type { VixEventTopTrade, VixOptionContractKline } from '../types/research'

const props = defineProps<{
  trades: VixEventTopTrade[]
  signalDate: string
}>()

const expandedTradeKey = ref('')
const loadingTradeKey = ref('')
const tradesScrollRef = ref<HTMLDivElement | null>(null)
const klineCache = ref<Record<string, VixOptionContractKline>>({})
const klineErrors = ref<Record<string, string>>({})

function tradeKey(trade: VixEventTopTrade) {
  return `${trade.exchange}:${trade.long_contract_code}`
}

async function toggleTradeKline(trade: VixEventTopTrade) {
  const key = tradeKey(trade)
  if (expandedTradeKey.value === key) {
    expandedTradeKey.value = ''
    return
  }
  expandedTradeKey.value = key
  await nextTick()
  tradesScrollRef.value?.scrollTo({ left: 0 })
  const outerScroll = tradesScrollRef.value?.closest('.research-table-wrap') as HTMLElement | null
  outerScroll?.scrollTo({ left: 0 })
  if (klineCache.value[key] || loadingTradeKey.value === key) return
  loadingTradeKey.value = key
  delete klineErrors.value[key]
  try {
    klineCache.value[key] = await fetchVixOptionContractKline(trade.exchange, trade.long_contract_code)
  } catch (error: any) {
    klineErrors.value[key] = error?.response?.data?.detail || error?.message || '期权K线加载失败'
  } finally {
    if (loadingTradeKey.value === key) loadingTradeKey.value = ''
  }
}

watch(
  () => [props.signalDate, ...props.trades.map(tradeKey)],
  () => {
    expandedTradeKey.value = ''
  },
)

function percent(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(digits)}%`
}

function strike(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(value >= 100 ? 0 : 3)
}

function exchangeLabel(value: string) {
  if (value === 'SSE') return '上交所'
  if (value === 'SZSE') return '深交所'
  if (value === 'CFFEX') return '中金所'
  return value
}

function strategyLabel(value: string) {
  return value === 'long_put' ? '单买认沽' : '单买认购'
}
</script>

<template>
  <div v-if="trades.length" class="event-top-trades">
    <div class="event-top-trades-head">
      <strong>该日回望收益前十</strong>
      <span>只说明历史上哪张期权收益最高，不代表实时可预知</span>
    </div>
    <div ref="tradesScrollRef" class="event-top-trades-scroll">
      <table>
        <thead>
          <tr><th>排名</th><th>产品</th><th>方向</th><th>到期</th><th>行权档位</th><th>持有</th><th>净收益</th><th>MAE</th><th>具体合约</th><th>K线</th></tr>
        </thead>
        <tbody>
          <template v-for="(trade, index) in trades" :key="`${trade.long_contract_code}-${trade.holding_days}`">
            <tr :class="{ 'is-expanded': expandedTradeKey === tradeKey(trade) }">
              <td>{{ index + 1 }}</td>
              <td>{{ exchangeLabel(trade.exchange) }} {{ trade.product_name }}</td>
              <td>{{ strategyLabel(trade.strategy_type) }}</td>
              <td>{{ trade.contract_month_label || trade.expiry_bucket_label || trade.dte_bucket || '-' }}</td>
              <td>{{ trade.long_strike_label || trade.moneyness_label || '-' }} / {{ strike(trade.long_strike) }}</td>
              <td>{{ trade.holding_days }}日</td>
              <td class="return-value">{{ percent(trade.net_return) }}</td>
              <td>{{ percent(trade.mae) }}</td>
              <td><button type="button" class="contract-link" @click="toggleTradeKline(trade)">{{ trade.long_contract_code }}</button></td>
              <td><button type="button" class="kline-toggle" @click="toggleTradeKline(trade)">{{ expandedTradeKey === tradeKey(trade) ? '收起' : '查看K线' }}</button></td>
            </tr>
            <tr v-if="expandedTradeKey === tradeKey(trade)" class="kline-detail-row">
              <td colspan="10">
                <div class="kline-panel">
                  <header>
                    <div><strong>{{ exchangeLabel(trade.exchange) }} {{ trade.product_name }} {{ trade.long_contract_code }}</strong><span>信号日 {{ signalDate.slice(0, 10) }}</span></div>
                    <div><span>买入 {{ trade.entry_date?.slice(0, 10) || '-' }}</span><span>卖出 {{ trade.exit_date?.slice(0, 10) || '-' }}</span></div>
                  </header>
                  <div v-if="loadingTradeKey === tradeKey(trade)" class="kline-status">正在加载真实期权日K...</div>
                  <div v-else-if="klineErrors[tradeKey(trade)]" class="kline-status error">{{ klineErrors[tradeKey(trade)] }}</div>
                  <OptionContractKlineChart
                    v-else-if="klineCache[tradeKey(trade)]"
                    :candles="klineCache[tradeKey(trade)].candles"
                    :signal-date="signalDate"
                    :exit-date="trade.exit_date"
                  />
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
  <p v-else class="empty-trades">该事件没有满足成交与到期约束的期权记录。</p>
</template>

<style scoped>
.event-top-trades { padding: 14px 0 4px; }
.event-top-trades-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.event-top-trades-head strong { color: #1e293b; }
.event-top-trades-head span { color: #64748b; font-size: 12px; }
.event-top-trades-scroll { overflow-x: auto; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; }
table { width: 100%; min-width: 1050px; border-collapse: collapse; }
th, td { padding: 9px 11px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 12px; white-space: nowrap; }
th { background: #f8fafc; color: #475569; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr.is-expanded td { background: #f8fbff; }
.return-value { color: #166534; font-weight: 800; }
.contract-link { padding: 0; border: 0; background: transparent; color: #1d4ed8; font: inherit; font-weight: 700; text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.kline-toggle { min-height: 28px; padding: 0 9px; border: 1px solid #93c5fd; border-radius: 5px; background: #eff6ff; color: #1d4ed8; font-size: 12px; font-weight: 800; cursor: pointer; }
.kline-detail-row td { position: sticky; left: 0; padding: 0; white-space: normal; background: #f8fafc; }
.kline-panel { box-sizing: border-box; width: min(100%, calc(100vw - 96px)); max-width: 1100px; min-height: 390px; padding: 14px; }
.kline-panel header { display: flex; justify-content: space-between; gap: 16px; min-height: 40px; margin-bottom: 8px; }
.kline-panel header div { display: flex; align-items: baseline; gap: 14px; }
.kline-panel header strong { color: #1e293b; }
.kline-panel header span { color: #64748b; font-size: 12px; }
.kline-panel header div:first-child span { color: #b45309; font-weight: 800; }
.kline-status { display: grid; place-items: center; height: 320px; color: #64748b; }
.kline-status.error { color: #b91c1c; }
.empty-trades { margin: 12px 0 0; color: #64748b; }
@media (max-width: 700px) {
  .event-top-trades-head { align-items: flex-start; flex-direction: column; gap: 4px; }
  .kline-panel { width: calc(100vw - 64px); padding: 10px; }
  .kline-panel header, .kline-panel header div { align-items: flex-start; flex-direction: column; gap: 4px; }
}
</style>
