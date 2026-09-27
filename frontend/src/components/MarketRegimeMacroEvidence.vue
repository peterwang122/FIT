<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { fetchMarketRegimeMacroEvidence } from '../api/marketRegime'
import type { MacroCycleEvidence, MacroEvidenceResponse, MarketRegimeResearch } from '../types/marketRegime'

const props = defineProps<{ date: string; research: MarketRegimeResearch | null }>()
const evidence = shallowRef<MacroEvidenceResponse | null>(null)
const loading = ref(false)
const error = ref('')
const archive = ref(false)
const category = ref('money')
let request: AbortController | null = null
let sequence = 0
const groups = [
  { key: 'money', label: '货币与信用' }, { key: 'activity', label: '经济景气' },
  { key: 'prices', label: '物价' }, { key: 'profit', label: '企业盈利' },
]
const labels: Record<string, string> = {
  m1_balance: 'M1余额', m1_yoy: 'M1同比', m2_balance: 'M2余额', m2_yoy: 'M2同比',
  tsf_stock: '社融存量', tsf_stock_yoy: '社融存量同比', tsf_flow: '社融增量',
  tsf_government_bond_flow: '政府债券融资', tsf_government_bond_stock: '政府债券存量',
  tsf_rmb_loan_flow: '社融人民币贷款增量', tsf_rmb_loan_stock: '社融人民币贷款存量',
  tsf_fx_loan_flow: '外币贷款增量', tsf_fx_loan_stock: '外币贷款存量',
  tsf_corporate_bond_flow: '企业债券融资', tsf_corporate_bond_stock: '企业债券存量',
  tsf_entrusted_loan_flow: '委托贷款增量', tsf_entrusted_loan_stock: '委托贷款存量',
  tsf_trust_loan_flow: '信托贷款增量', tsf_trust_loan_stock: '信托贷款存量',
  tsf_bank_acceptance_flow: '未贴现银行承兑汇票增量', tsf_bank_acceptance_stock: '未贴现银行承兑汇票存量',
  tsf_equity_flow: '非金融企业境内股票融资', tsf_equity_stock: '非金融企业境内股票融资存量',
  loan_household_mlt: '居民中长期贷款', loan_household_short: '居民短期贷款',
  loan_corporate_mlt: '企业中长期贷款', loan_corporate_short: '企业短期贷款', loan_corporate_bills: '票据融资',
  pmi_manufacturing: '制造业PMI', pmi_production: 'PMI生产', pmi_new_orders: 'PMI新订单',
  pmi_nonmanufacturing: '非制造业商务活动', cpi_yoy: 'CPI同比', cpi_mom: 'CPI环比',
  core_cpi_yoy: '核心CPI同比', ppi_yoy: 'PPI同比', ppi_mom: 'PPI环比',
  industrial_profit_ytd: '工业企业利润累计', industrial_profit_ytd_yoy: '工业企业利润累计同比',
  industrial_profit_month_yoy: '工业企业利润当月同比', industrial_revenue_ytd: '工业企业营收累计',
  industrial_revenue_ytd_yoy: '工业企业营收累计同比',
}
const rows = computed(() => (archive.value ? evidence.value?.archive_macro_evidence : evidence.value?.macro_evidence) ?? [])
const categoryOf = (key: string) => key.startsWith('pmi_') ? 'activity' : key.startsWith('industrial_') ? 'profit' : /^(core_cpi|cpi|ppi)/.test(key) ? 'prices' : 'money'
const filtered = computed(() => rows.value.filter(row => categoryOf(row.series_key) === category.value))
const latest = (key: string) => rows.value.filter(r => r.series_key === key).sort((a, b) => b.period_end.localeCompare(a.period_end))[0]
const highlights = computed(() => ['m1_yoy', 'm2_yoy', 'tsf_stock_yoy', 'pmi_manufacturing', 'core_cpi_yoy', 'industrial_profit_ytd_yoy'].map(key => ({ key, row: latest(key) })))
function format(value: number | null | undefined, unit: string, change = false) {
  if (value == null) return '无可核验数据'
  if (unit === 'CNY') return `${(value / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}亿元`
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${change && unit === '%' ? 'pp' : unit === 'points' ? '点' : unit}`
}
function period(row: MacroCycleEvidence) {
  const kind = row.period_kind === 'ytd' ? `1–${Number(row.period_end.slice(5, 7))}月累计` : row.period_kind === 'stock' ? '月末存量' : '当月'
  return `${row.period_end.slice(0, 7)} · ${kind}`
}
const timestamp = (value: string | null | undefined) => value?.replace('T', ' ').replace(/\+08:00$/, '') ?? '未核验'
async function load() {
  request?.abort()
  const current = ++sequence
  archive.value = false
  error.value = ''
  evidence.value = null
  if (!props.date) return
  if (props.research?.target_date === props.date) {
    evidence.value = props.research
    loading.value = false
    return
  }
  request = new AbortController()
  loading.value = true
  try {
    const response = await fetchMarketRegimeMacroEvidence(props.date, request.signal)
    if (current === sequence) evidence.value = response
  } catch {
    if (current === sequence && !request.signal.aborted) error.value = '宏观证据加载失败'
  } finally {
    if (current === sequence) loading.value = false
  }
}
watch(() => [props.date, props.research], load, { immediate: true })
onBeforeUnmount(() => { sequence++; request?.abort() })
</script>

<template>
  <section class="macro-evidence" data-testid="regime-macro-evidence">
    <div class="evidence-head"><h3>宏观证据 <small>{{ date }} · 已锁定</small></h3><span>截至 {{ timestamp(evidence?.as_of_at) }}（北京时间）</span></div>
    <p class="explanation">官方月度数据按发布时间延用，不依赖逐股采集；货币信用、景气和盈利参与结构确认。物价及其他分项保留解释，不重复加权。</p>
    <p v-if="loading" role="status">正在读取该时点已知数据…</p>
    <p v-else-if="error" role="alert">{{ error }} <button @click="load">重试</button></p>
    <template v-else-if="evidence">
      <p v-if="!evidence.macro_complete" class="evidence-warning">严格时点证据不完整：{{ [...evidence.missing_macro, ...evidence.stale_macro].map(key => labels[key] ?? key).join('、') }}。历史归档不冒充当时已知数据。</p>
      <label v-if="!evidence.macro_complete && evidence.archive_macro_evidence?.length" class="archive-toggle"><input v-model="archive" type="checkbox" /> 查看历史归档参考（不用于实时回测）</label>
      <p v-if="archive" class="evidence-warning">当前为事后归档参考，可能包含后来核验或修订的值，不参与市场环境和策略收益计算。</p>
      <div class="macro-highlights">
        <div v-for="item in highlights" :key="item.key" class="macro-reading"><span>{{ labels[item.key] }}</span><strong>{{ format(item.row?.value, item.row?.unit ?? '%') }}</strong><small>{{ item.row ? period(item.row) : '当时版本尚不可核验' }}</small></div>
      </div>
      <div class="evidence-head"><div class="macro-tabs" role="tablist" aria-label="宏观证据类别"><button v-for="group in groups" :key="group.key" role="tab" :aria-selected="category === group.key" @click="category = group.key">{{ group.label }}</button></div><span>{{ rows.length }}条{{ archive ? '归档参考' : '可见证据' }}</span></div>
      <div class="macro-table-wrap"><table><thead><tr><th>指标 / 口径</th><th>所属期</th><th>官方值</th><th>较3个月前</th><th>实际可用时间 / 来源</th></tr></thead><tbody>
        <tr v-for="row in filtered" :key="`${row.series_key}:${row.period_kind}:${row.basis_version}`">
          <td>{{ labels[row.series_key] ?? row.series_key }}<small v-if="row.basis_version === 'm1_2025'">2025年起新口径</small><small v-else-if="row.basis_version === 'm1_legacy'">旧口径，仅历史参考</small><small v-if="row.revision">官方修订版本</small><small v-if="row.parser_correction">解析修订版本</small></td>
          <td>{{ period(row) }}</td><td :title="`${row.value} ${row.unit}`">{{ format(row.value, row.unit) }}</td>
          <td>{{ row.period_kind === 'ytd' ? '累计值不作月度差分' : row.basis_version === 'm1_legacy' ? '不跨口径比较' : format(row.change_3m, row.unit, true) }}</td>
          <td><a :href="row.source_url" target="_blank" rel="noopener noreferrer">{{ timestamp(row.available_at) }}</a><small v-if="row.period_age_days != null && row.period_age_days > 100">历史口径 / 较早所属期</small><small>{{ row.point_in_time_verified ? '当时已知版本' : '事后归档参考' }}</small></td>
        </tr>
        <tr v-if="!filtered.length"><td colspan="5">该时点无可核验证据</td></tr>
      </tbody></table></div>
      <p v-if="!archive" class="derived" v-for="item in evidence.derived_evidence ?? []" :key="item.series_key">{{ item.label }}：{{ format(item.value, item.unit) }}（{{ item.period_end.slice(0, 7) }}）</p>
    </template>
  </section>
</template>

<style scoped>
.macro-evidence { min-width: 0; border-top: 1px solid #dce3eb; padding-top: 14px; }
.evidence-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
h3 { font-size: 16px; margin: 0; } h3 small, .evidence-head > span { font-size: 12px; color: #64748b; font-weight: 400; }
.explanation, .derived, .archive-toggle { font-size: 12px; line-height: 1.7; color: #64748b; margin: 8px 0; }
.evidence-warning { font-size: 12px; line-height: 1.7; color: #805b19; }
.macro-highlights { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; margin: 16px 0; }
.macro-reading { min-width: 0; border-left: 2px solid #bacbdc; padding-left: 12px; }
.macro-reading span, .macro-reading small { display: block; font-size: 12px; color: #64748b; }
.macro-reading strong { display: block; font-size: 21px; margin: 6px 0; overflow-wrap: anywhere; }
.macro-tabs { display: flex; flex-wrap: wrap; gap: 20px; }
.macro-tabs button { border: 0; border-bottom: 2px solid transparent; background: transparent; padding: 8px 0; font: inherit; font-size: 14px; color: #64748b; cursor: pointer; }
.macro-tabs button[aria-selected="true"] { border-bottom-color: #0f4c75; color: #0f4c75; }
.macro-table-wrap { max-height: 460px; overflow: auto; margin-top: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; line-height: 1.6; }
th { background: #f3f6fa; color: #64748b; position: sticky; top: 0; font-weight: 500; }
td small { display: block; color: #64748b; } a { color: #0f4c75; }
@media (max-width: 1280px) { .macro-highlights { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 800px) { table { min-width: 660px; } .macro-highlights { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
