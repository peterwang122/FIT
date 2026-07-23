<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { fetchCsi1000FuturesAnalysis } from '../api/research'
import Csi1000FuturesSignalChart from '../components/Csi1000FuturesSignalChart.vue'
import type {
  Csi1000FuturesContractResult,
  Csi1000FuturesReport,
  Csi1000FuturesWave,
} from '../types/research'

type Direction = 'up' | 'down'

const report = ref<Csi1000FuturesReport | null>(null)
const loading = ref(true)
const error = ref('')
const activeDirection = ref<Direction>('up')
const selectedWaveId = ref<number | null>(null)
const expandedResults = ref<string[]>([])

const directionWaves = computed(() =>
  (report.value?.waves ?? []).filter((item) => item.direction === activeDirection.value),
)
const selectedWave = computed<Csi1000FuturesWave | null>(() =>
  directionWaves.value.find((item) => item.wave_id === selectedWaveId.value) ?? null,
)
const directionSummary = computed(() => report.value?.direction_summaries[activeDirection.value] ?? null)
const bestResult = computed(() =>
  selectedWave.value?.contract_results.find(
    (item) => item.result_id === selectedWave.value?.best_result_id,
  ) ?? null,
)

watch(activeDirection, selectLatestWave)

function selectLatestWave() {
  const completed = directionWaves.value.filter((item) => item.complete)
  selectedWaveId.value =
    completed[completed.length - 1]?.wave_id ??
    directionWaves.value[directionWaves.value.length - 1]?.wave_id ??
    null
  expandedResults.value = []
}

function money(value: number | null | undefined, sign = false) {
  if (value == null || !Number.isFinite(value)) return '-'
  const prefix = sign && value > 0 ? '+' : ''
  return `${prefix}${value.toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  })}`
}

function number(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '-'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function percent(value: number | null | undefined, ratio = false) {
  if (value == null || !Number.isFinite(value)) return '-'
  return `${(ratio ? value * 100 : value).toFixed(2)}%`
}

function dateText(value: string | null | undefined) {
  return value?.slice(0, 10) || '-'
}

function toggleResult(item: Csi1000FuturesContractResult) {
  expandedResults.value = expandedResults.value.includes(item.result_id)
    ? expandedResults.value.filter((key) => key !== item.result_id)
    : [...expandedResults.value, item.result_id]
}

function isExpanded(item: Csi1000FuturesContractResult) {
  return expandedResults.value.includes(item.result_id)
}

function contractPathText(item: Csi1000FuturesContractResult) {
  if (!item.valid) return item.reason || '不可计算'
  return item.contract_path
    .map((segment) => `${segment.contract}（${dateText(segment.start_date)}~${dateText(segment.end_date)}）`)
    .join(' → ')
}

function entryAction(direction: Direction) {
  return direction === 'up' ? '最低价做多' : '最高价做空'
}

function exitAction(direction: Direction) {
  return direction === 'up' ? '最高价平多' : '最低价平空'
}

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    report.value = await fetchCsi1000FuturesAnalysis()
    selectLatestWave()
  } catch (rawError) {
    error.value =
      (rawError as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      (rawError instanceof Error ? rawError.message : '研究报告加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadReport)
</script>

<template>
  <section class="futures-research">
    <p v-if="loading" class="research-state muted">中证1000波段期货研究加载中...</p>
    <div v-else-if="error" class="research-state error-state">
      <strong>{{ error }}</strong>
      <button type="button" class="btn secondary" @click="loadReport">重新加载</button>
    </div>
    <template v-else-if="report">
      <header class="futures-head">
        <div>
          <p class="eyebrow">中证1000 · IM数字合约</p>
          <h3>{{ report.title }}</h3>
          <p class="muted">
            {{ report.data_range.start }} 至 {{ report.data_range.end }} ·
            20% ZigZag · 更新时间 {{ new Date(report.generated_at).toLocaleString('zh-CN') }}
          </p>
        </div>
        <div class="direction-switch" aria-label="波段方向">
          <button type="button" :class="{ active: activeDirection === 'up' }" @click="activeDirection = 'up'">上涨波段</button>
          <button type="button" :class="{ active: activeDirection === 'down' }" @click="activeDirection = 'down'">下跌波段</button>
        </div>
      </header>

      <section class="scope-strip">
        <div><span>全部波段</span><strong>{{ report.sample.wave_count }}</strong></div>
        <div><span>上涨波段</span><strong>{{ report.sample.up_wave_count }}</strong></div>
        <div><span>下跌波段</span><strong>{{ report.sample.down_wave_count }}</strong></div>
        <div><span>已确认</span><strong>{{ report.sample.completed_wave_count }}</strong></div>
        <div><span>尚未确认</span><strong>{{ report.sample.provisional_wave_count }}</strong></div>
        <div><span>当前方向样本</span><strong>{{ directionSummary?.wave_count ?? 0 }}</strong></div>
      </section>

      <section class="wave-selector-band">
        <div class="section-head">
          <div>
            <h4>{{ activeDirection === 'up' ? '上涨波段' : '下跌波段' }}</h4>
            <p class="muted">每个按钮是一段由反向20%行情确认的独立波段；虚线按钮表示最后一段尚未确认。</p>
          </div>
          <div class="wave-switch">
            <button
              v-for="wave in directionWaves"
              :key="wave.wave_id"
              type="button"
              :class="{ active: selectedWaveId === wave.wave_id, provisional: !wave.complete }"
              @click="selectedWaveId = wave.wave_id; expandedResults = []"
            >
              波段{{ wave.wave_id }} · {{ dateText(wave.start_date) }}
            </button>
          </div>
        </div>
      </section>

      <template v-if="selectedWave">
        <section class="wave-summary">
          <div><span>方向</span><strong>{{ selectedWave.direction_label }}</strong><small>{{ selectedWave.complete ? '已由反向20%确认' : '当前暂定波段' }}</small></div>
          <div><span>起点</span><strong>{{ number(selectedWave.start_value) }}</strong><small>{{ selectedWave.start_date }} · {{ selectedWave.start_kind === 'low' ? '低点' : '高点' }}</small></div>
          <div><span>终点</span><strong>{{ number(selectedWave.end_value) }}</strong><small>{{ selectedWave.end_date }} · {{ selectedWave.end_kind === 'low' ? '低点' : '高点' }}</small></div>
          <div><span>指数变化</span><strong>{{ percent(selectedWave.index_change_pct) }}</strong><small>绝对幅度 {{ percent(selectedWave.amplitude_pct) }}</small></div>
          <div><span>确认日期</span><strong>{{ dateText(selectedWave.confirmation_date) }}</strong><small>达到反向20%的交易日</small></div>
          <div><span>起点挂牌合约</span><strong>{{ selectedWave.contract_results.length }}</strong><small>全部逐份计算</small></div>
        </section>

        <section class="chart-band">
          <div class="section-head">
            <div>
              <h4>波段{{ selectedWave.wave_id }}：中证1000高低点</h4>
              <p class="muted">绿色为低点，琥珀色为高点；图上不再展示任何策略信号。</p>
            </div>
            <div class="point-legend"><span class="low">波段低点</span><span class="high">波段高点</span></div>
          </div>
          <Csi1000FuturesSignalChart :candles="report.index_candles" :wave="selectedWave" />
        </section>

        <section v-if="bestResult" class="best-band">
          <div>
            <span>{{ selectedWave.complete ? '本波段回望收益最高' : '暂定波段截至端点收益最高' }}</span>
            <h4>{{ bestResult.start_contract }} · {{ bestResult.tenor_label }}</h4>
            <p>起点到期日 {{ bestResult.start_expiry }}；{{ entryAction(selectedWave.direction) }}，仅到期后续接近月。</p>
          </div>
          <dl>
            <div><dt>净收益</dt><dd>{{ money(bestResult.net_pnl, true) }}</dd></div>
            <div><dt>期货点数</dt><dd>{{ number(bestResult.gross_points) }}</dd></div>
            <div><dt>到期续接</dt><dd>{{ bestResult.roll_count }}次</dd></div>
          </dl>
        </section>

        <section class="contract-band">
          <div class="section-head">
            <div>
              <h4>起点当日全部实际合约收益</h4>
              <p class="muted">不限制合约数量。点击任意一行查看到期结算、下一交易日续接及最终平仓的全部价格。</p>
            </div>
          </div>
          <div class="table-wrap">
            <table class="futures-table">
              <thead>
                <tr><th></th><th>排名</th><th>起始合约</th><th>到期日</th><th>入场</th><th>退出</th><th>续接</th><th>点数收益</th><th>净收益</th><th>名义收益率</th><th>完整持有路径</th></tr>
              </thead>
              <tbody>
                <template v-for="item in selectedWave.contract_results" :key="item.result_id">
                  <tr :class="['clickable', { best: item.result_id === selectedWave.best_result_id }]" @click="toggleResult(item)">
                    <td>{{ isExpanded(item) ? '−' : '+' }}</td>
                    <td>{{ item.rank ?? '-' }}</td>
                    <td><strong>{{ item.start_contract }}</strong><small>{{ item.tenor_label }}</small></td>
                    <td>{{ item.start_expiry }}</td>
                    <td>{{ number(item.entry_price) }}<small>{{ entryAction(selectedWave.direction) }}</small></td>
                    <td>{{ number(item.exit_price) }}<small>{{ item.exit_contract }} · {{ exitAction(selectedWave.direction) }}</small></td>
                    <td>{{ item.roll_count ?? '-' }}次</td>
                    <td>{{ number(item.gross_points) }}</td>
                    <td :class="['pnl', { positive: (item.net_pnl || 0) > 0 }]">{{ money(item.net_pnl, true) }}</td>
                    <td>{{ percent(item.notional_return_pct) }}</td>
                    <td class="path-cell">{{ contractPathText(item) }}</td>
                  </tr>
                  <tr v-if="isExpanded(item)" class="detail-row">
                    <td colspan="11">
                      <div v-if="!item.valid" class="invalid-detail">{{ item.reason }}</div>
                      <ol v-else class="path-detail">
                        <li v-for="segment in item.contract_path" :key="`${item.result_id}-${segment.contract}-${segment.start_date}`">
                          <strong>{{ segment.contract }}</strong>：{{ segment.start_date }} 以 {{ number(segment.entry_price) }} 建仓，
                          {{ segment.end_date }} 以 {{ number(segment.exit_price) }}
                          {{ segment.end_action === 'expiry' ? '到期结算' : segment.end_action === 'wave_end' ? '在波段终点平仓' : '按暂定端点平仓' }}
                        </li>
                      </ol>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <section class="aggregate-band">
        <div class="section-head">
          <div><h4>{{ activeDirection === 'up' ? '上涨' : '下跌' }}波段按到期顺序汇总</h4><p class="muted">只汇总已确认波段；“第N到期”按每个波段起点当天的实际挂牌顺序重新排列。</p></div>
        </div>
        <div class="table-wrap">
          <table class="futures-table">
            <thead><tr><th>起始位置</th><th>覆盖波段</th><th>累计净收益</th><th>平均每段</th><th>中位数</th><th>胜率</th><th>成为单段最优</th></tr></thead>
            <tbody>
              <tr v-for="item in directionSummary?.tenors" :key="item.tenor_index">
                <td>{{ item.tenor_label }}</td><td>{{ item.wave_count }}</td><td>{{ money(item.total_net_pnl, true) }}</td>
                <td>{{ money(item.average_net_pnl, true) }}</td><td>{{ money(item.median_net_pnl, true) }}</td><td>{{ percent(item.win_rate, true) }}</td><td>{{ item.best_wave_count }}次</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="method-band">
        <h4>研究口径</h4>
        <dl>
          <div><dt>波段</dt><dd>中证1000日K按20% ZigZag独立划分，不读取保存策略、情绪指标或红蓝信号。</dd></div>
          <div><dt>上涨段</dt><dd>低点日使用每份期货合约的当日最低价做多，高点日使用当日最高价平仓。</dd></div>
          <div><dt>下跌段</dt><dd>高点日使用每份期货合约的当日最高价做空，低点日使用当日最低价平仓。</dd></div>
          <div><dt>合约范围</dt><dd>波段起点当天所有实际挂牌、成交量大于0的IM数字合约，不限制为四份。</dd></div>
          <div><dt>换月</dt><dd>{{ report.methodology.roll }}，禁止到期前主动切换。</dd></div>
          <div><dt>成本</dt><dd>每点{{ report.methodology.multiplier }}元，按中金所手续费率回算；不加滑点和券商额外收费。</dd></div>
          <div><dt>重要限制</dt><dd>本研究已知波段高低点，并使用当日最有利成交价，只表示历史收益上限，不能作为实时可复制收益。</dd></div>
        </dl>
      </section>
    </template>
  </section>
</template>

<style scoped>
.futures-research { min-width: 0; color: #1e293b; }
.research-state { padding: 28px; border: 1px solid #dbe3ec; background: #fff; }
.error-state { display: flex; align-items: center; justify-content: space-between; color: #b91c1c; }
.futures-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 20px 22px; border: 1px solid #dbe3ec; background: #fff; }
.futures-head h3 { margin: 2px 0 7px; font-size: 22px; letter-spacing: 0; }.futures-head p { margin: 0; }
.eyebrow { color: #2563eb; font-size: 12px; font-weight: 800; }
.direction-switch, .wave-switch { display: flex; flex-wrap: wrap; gap: 4px; }
.direction-switch button, .wave-switch button { border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; color: #475569; padding: 8px 11px; cursor: pointer; font-weight: 800; }
.direction-switch button.active, .wave-switch button.active { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.wave-switch button.provisional { border-style: dashed; }.wave-switch button.provisional.active { border-style: solid; border-color: #d97706; background: #fffbeb; color: #92400e; }
.scope-strip { display: grid; grid-template-columns: repeat(6, 1fr); border: 1px solid #dbe3ec; border-top: 0; background: #f8fafc; }
.scope-strip div { padding: 12px 14px; border-right: 1px solid #e2e8f0; }.scope-strip div:last-child { border-right: 0; }
.scope-strip span, .scope-strip strong { display: block; }.scope-strip span { color: #64748b; font-size: 11px; }.scope-strip strong { margin-top: 3px; font-size: 17px; }
.wave-selector-band, .chart-band, .contract-band, .aggregate-band, .method-band { padding: 20px 22px; border: 1px solid #dbe3ec; border-top: 0; background: #fff; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }.section-head h4, .method-band h4 { margin: 0 0 4px; font-size: 17px; }.section-head p { margin: 0; }
.wave-summary { display: grid; grid-template-columns: repeat(6, 1fr); border: 1px solid #dbe3ec; border-top: 0; background: #fff; }
.wave-summary div { min-width: 0; padding: 13px 14px; border-right: 1px solid #e2e8f0; }.wave-summary div:last-child { border-right: 0; }
.wave-summary span, .wave-summary strong, .wave-summary small { display: block; }.wave-summary span, .wave-summary small { color: #64748b; }.wave-summary span { font-size: 11px; }.wave-summary strong { margin: 4px 0; font-size: 16px; }.wave-summary small { font-size: 11px; }
.point-legend { display: flex; gap: 12px; color: #64748b; font-size: 12px; }.point-legend span::before { content: ''; display: inline-block; width: 8px; height: 8px; margin-right: 5px; border-radius: 50%; }.point-legend .low::before { background: #059669; }.point-legend .high::before { background: #d97706; }
.best-band { display: grid; grid-template-columns: minmax(280px, 1fr) minmax(380px, .8fr); gap: 24px; padding: 18px 22px; border: 1px solid #dbe3ec; border-top: 0; background: #f0fdf4; }
.best-band span { color: #047857; font-size: 11px; font-weight: 800; }.best-band h4 { margin: 5px 0; font-size: 18px; }.best-band p { margin: 0; color: #64748b; }
.best-band dl { display: grid; grid-template-columns: repeat(3, 1fr); margin: 0; }.best-band dl div { padding: 5px 12px; border-left: 1px solid #bbf7d0; }.best-band dt { color: #64748b; font-size: 11px; }.best-band dd { margin: 4px 0 0; font-weight: 800; }
.table-wrap { max-width: 100%; overflow: auto; border: 1px solid #dbe3ec; }.futures-table { width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }
.futures-table th { position: sticky; top: 0; z-index: 1; padding: 9px 10px; border-bottom: 1px solid #cbd5e1; background: #f1f5f9; color: #475569; text-align: left; }.futures-table td { padding: 9px 10px; border-bottom: 1px solid #e2e8f0; }.futures-table td small { display: block; margin-top: 3px; color: #64748b; }.futures-table tbody tr:last-child td { border-bottom: 0; }
.clickable { cursor: pointer; }.clickable:hover td { background: #f8fafc; }.clickable.best td { background: #f0fdf4; }.path-cell { min-width: 420px; max-width: 650px; white-space: normal; line-height: 1.55; }.pnl { color: #059669; font-weight: 800; }.pnl.positive { color: #dc2626; }
.detail-row td { padding: 0; background: #f8fafc; }.path-detail { margin: 0; padding: 14px 22px 14px 40px; white-space: normal; line-height: 1.85; }.invalid-detail { padding: 14px 18px; color: #b91c1c; }
.method-band dl { margin: 12px 0 0; border-top: 1px solid #dbe3ec; }.method-band dl div { display: grid; grid-template-columns: 110px 1fr; gap: 18px; padding: 11px 0; border-bottom: 1px solid #e2e8f0; }.method-band dt { color: #64748b; font-size: 12px; }.method-band dd { margin: 0; line-height: 1.65; }
@media (max-width: 1050px) { .scope-strip, .wave-summary { grid-template-columns: repeat(3, 1fr); }.best-band { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .futures-head, .section-head { flex-direction: column; }.scope-strip, .wave-summary, .best-band dl { grid-template-columns: repeat(2, 1fr); }.best-band { grid-template-columns: 1fr; }.method-band dl div { grid-template-columns: 1fr; gap: 5px; } }
</style>
