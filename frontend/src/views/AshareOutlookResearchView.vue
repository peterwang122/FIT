<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchAshareOutlook } from '../api/research'
import AshareOutlookChart from '../components/AshareOutlookChart.vue'
import AshareHistoricalComparison from '../components/AshareHistoricalComparison.vue'
import type { AshareOutlookReport } from '../types/research'

const report = ref<AshareOutlookReport | null>(null)
const loading = ref(true)
const error = ref('')
const indexCode = ref('sh000985')
const selected = computed(() => report.value?.indexes.find(i => i.index_code === indexCode.value) ?? report.value?.indexes[0])
const sourceMap = computed(() => new Map(report.value?.sources.map(s => [s.id, s]) ?? []))
const number = (value: number | null | undefined, digits = 2) => value == null ? '待验证' : value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const percent = (value: number | null | undefined) => value == null ? '待验证' : `${value > 0 ? '+' : ''}${number(value)}%`
const dateTime = (value: string | null | undefined) => value ? value.replace('T', ' ').replace('+08:00', ' 北京时间') : '发布时间未核验'

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await fetchAshareOutlook()
  } catch (e) {
    error.value = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'A股市场展望加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <section class="outlook-research">
    <p v-if="loading" class="muted state" role="status">A股市场展望加载中...</p>
    <div v-else-if="error" class="state error" role="alert">
      <p>{{ error }}</p><button class="btn secondary" type="button" @click="load">重新加载</button>
    </div>
    <template v-else-if="report && selected">
      <header class="report-head">
        <div><h3>{{ report.title }}</h3><p class="muted">研究截止 {{ dateTime(report.as_of_at) }} · A股行情 {{ report.market_date }}</p></div>
        <span class="version">日期固定研究 · 非交易信号</span>
      </header>
      <section class="summary-band" aria-label="研究结论">
        <div v-for="item in report.summary" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><p>{{ item.detail }}</p></div>
      </section>
      <p class="quality-notice">国庆休市期间外盘信息单列，不回填9月30日。融资使用前一交易日数据：{{ report.financing?.source_date ?? '缺失' }}<template v-if="report.financing?.status === 'available_lagged'">（正常发布滞后，可用）</template>。旧风险总分未重算；价格区间为条件情景，不保证底部。</p>

      <section class="chart-band">
        <div class="section-heading">
          <h4>价格结构与已发生的低点</h4>
          <div class="index-switch" role="group" aria-label="研究指数">
            <button v-for="index in report.indexes" :key="index.index_code" :aria-pressed="indexCode === index.index_code" :class="{ active: indexCode === index.index_code }" type="button" @click="indexCode = index.index_code">{{ index.index_name }}</button>
          </div>
        </div>
        <AshareOutlookChart :index="selected" />
        <div class="chart-facts"><span>{{ selected.index_name }} {{ number(selected.close) }}</span><span>本轮最高 {{ number(selected.cycle_peak) }} · {{ selected.cycle_peak_date }}</span><span>高点回撤 {{ percent(selected.cycle_drawdown_pct) }}</span><span>MA250 20日斜率 {{ percent(selected.ma250_slope_20d_pct) }}</span></div>
        <small class="muted">来源 {{ selected.data_source }} · {{ selected.source_date }}；价格指数，不含分红。均线不是未来支撑保证。</small>
      </section>
      <div class="table-scroll">
        <table><caption>五条宽基的共同日期比较</caption><thead><tr><th>指数</th><th>收盘</th><th>MA60</th><th>MA120</th><th>MA250</th><th>20日涨跌</th><th>距本轮高点</th></tr></thead>
          <tbody><tr v-for="index in report.indexes" :key="index.index_code"><th>{{ index.index_name }}</th><td>{{ number(index.close) }}</td><td>{{ number(index.ma60) }}</td><td>{{ number(index.ma120) }}</td><td>{{ number(index.ma250) }}</td><td>{{ percent(index.return_20d_pct) }}</td><td>{{ percent(index.cycle_drawdown_pct) }}</td></tr></tbody>
        </table>
      </div>

      <div class="reading-layout">
        <nav class="contents" aria-label="研究目录">
          <a v-for="section in report.sections" :key="section.id" :href="`#outlook-${section.id}`">{{ section.title }}</a>
          <a href="#outlook-watchlist">条件检查清单</a><a href="#outlook-sources">来源与数据边界</a>
        </nav>
        <article class="report-body">
          <section v-for="section in report.sections" :id="`outlook-${section.id}`" :key="section.id" class="research-section">
            <h4>{{ section.title }}</h4><p class="verdict">{{ section.verdict }}</p>
            <p v-for="(paragraph, n) in section.paragraphs" :key="n" class="research-paragraph">
              <span class="kind" :class="{ hypothesis: paragraph.kind === '情景' }">{{ paragraph.kind }}</span>{{ paragraph.text }}
              <span v-if="paragraph.sources.length" class="citations"><a v-for="id in paragraph.sources" :key="id" :href="sourceMap.get(id)?.url" target="_blank" rel="noopener noreferrer">{{ sourceMap.get(id)?.title }}</a></span>
            </p>

            <div v-for="(evidence, n) in section.tables ?? []" :key="n" class="extension-evidence">
              <div class="table-scroll"><table>
                <caption>{{ evidence.title }}</caption>
                <thead><tr><th v-for="(column, c) in evidence.columns" :key="c" scope="col">{{ column }}</th></tr></thead>
                <tbody><tr v-for="(row, r) in evidence.rows" :key="r"><template v-for="(cell, c) in row" :key="c"><th v-if="c === 0" scope="row">{{ cell }}</th><td v-else>{{ cell }}</td></template></tr></tbody>
              </table></div>
              <p class="muted">{{ evidence.note }}</p>
            </div>

            <template v-if="section.id === 'history' && report.history_comparison">
              <AshareHistoricalComparison :comparison="report.history_comparison.spring_2021" />
              <div class="table-scroll"><table><caption>2021年：全年与春节后分别计算，不混用起点</caption>
                <thead><tr><th>资产</th><th>全年涨跌</th><th>春节前至3月9日</th><th>春节前至年底</th><th>3月9日至年底</th><th>全年日内高点日期</th></tr></thead><tbody>
                  <tr v-for="row in report.history_comparison.spring_2021.rows" :key="row.code"><th>{{ row.name }}</th><td>{{ percent(row.year_return_pct) }}</td><td>{{ percent(row.spring_to_march_pct) }}</td><td>{{ percent(row.spring_to_end_pct) }}</td><td>{{ percent(row.march_to_end_pct) }}</td><td>{{ row.peak_date ?? '缺失' }}</td></tr>
                </tbody></table></div>
              <div class="table-scroll"><table><caption>五宽基参与状态：不是个股广度</caption>
                <thead><tr><th>交易日</th><th>MA60上方</th><th>MA250上方</th><th>年线仍上行</th><th>近20日上涨</th></tr></thead><tbody>
                  <tr v-for="row in report.history_comparison.panels" :key="row.date"><th>{{ row.date }}</th><td>{{ row.above_ma60_count }}/5</td><td>{{ row.above_ma250_count }}/5</td><td>{{ row.rising_ma250_count }}/5</td><td>{{ row.positive_20d_count }}/5</td></tr>
                </tbody></table></div>
              <div class="table-scroll"><table><caption>多轮次情境对照：事后选定区间，不比较胜率或拟合牛熊概率</caption>
                <thead><tr><th>案例 / 起止</th><th>上证</th><th>全指</th><th>沪深300</th><th>中证500</th><th>中证1000</th></tr></thead><tbody>
                  <template v-for="case_ in report.history_comparison.cases" :key="case_.id">
                    <tr><th>{{ case_.title }}<small>{{ case_.start }} 至 {{ case_.end }}</small></th><td v-for="row in case_.rows" :key="row.index_code">{{ percent(row.return_pct) }}</td></tr>
                    <tr v-if="case_.rebound_end"><th>其中：反弹阶段<small>{{ case_.start }} 至 {{ case_.rebound_end }}</small></th><td v-for="row in case_.rebound_rows" :key="row.index_code">{{ percent(row.return_pct) }}</td></tr>
                  </template>
                </tbody></table></div>
              <details><summary>五宽基同步失守后的全部事件与反例</summary>
                <p class="muted">{{ report.history_comparison.synchronized_breaks.method }}</p>
                <p class="muted">{{ report.history_comparison.synchronized_breaks.note }}</p>
                <div class="table-scroll"><table><thead><tr><th>触发日</th><th>20日期末</th><th>20日最低价变化</th><th>60日期末</th><th>60日最低价变化</th><th>120日期末</th><th>120日最低价变化</th></tr></thead><tbody>
                  <tr v-for="row in report.history_comparison.synchronized_breaks.events" :key="row.date"><th>{{ row.date }}</th><td>{{ percent(row.return_20d_pct) }}</td><td>{{ percent(row.lowest_20d_pct) }}</td><td>{{ percent(row.return_60d_pct) }}</td><td>{{ percent(row.lowest_60d_pct) }}</td><td>{{ percent(row.return_120d_pct) }}</td><td>{{ percent(row.lowest_120d_pct) }}</td></tr>
                </tbody></table></div>
              </details>
              <ul class="quality-list"><li v-for="note in report.history_comparison.limitations" :key="note">{{ note }}</li></ul>
            </template>

            <template v-if="section.id === 'bottom'">
              <div class="table-scroll"><table><caption>{{ selected.index_name }} · 观察锚与压力刻度（非目标价）</caption>
                <thead><tr><th>性质</th><th>来源/假设</th><th>点位</th><th>距当前</th></tr></thead>
                <tbody><tr v-for="anchor in selected.anchors" :key="anchor.label"><td>已发生的低点</td><th>{{ anchor.label }}<small>{{ anchor.date }} · {{ anchor.status }}</small></th><td>{{ number(anchor.value) }}</td><td>{{ percent(anchor.distance_pct) }}</td></tr>
                  <tr v-for="stress in selected.stress_levels" :key="stress.peak_drawdown_pct" class="stress-row"><td>算术压力</td><th>高点回撤{{ stress.peak_drawdown_pct }}%</th><td>{{ number(stress.value) }}</td><td>{{ percent(stress.distance_pct) }}</td></tr></tbody>
              </table></div>
            </template>
            <template v-if="section.id === 'money'">
              <div class="table-scroll"><table><caption>月度宏观证据（所属期不等于发布日期）</caption><thead><tr><th>指标</th><th>官方值</th><th>三个月变化</th><th>所属期/口径</th><th>可用时间</th></tr></thead>
                <tbody><tr v-for="m in report.monthly_macro" :key="m.series_key"><th><a :href="m.source_url" target="_blank" rel="noopener noreferrer">{{ m.name }}</a></th><td>{{ number(m.value, 1) }}{{ m.unit }}</td><td>{{ number(m.change_3m, 1) }}pp</td><td>{{ m.period_end }}<small>{{ m.period_kind === 'ytd' ? '累计同比' : '月度' }} · {{ m.basis_version }}</small></td><td>{{ dateTime(m.available_at) }}</td></tr></tbody>
              </table></div>
            </template>
            <template v-if="section.id === 'valuation'">
              <div class="table-scroll"><table><caption>盈利与估值压力敏感性：假设，不是公允价值</caption><thead><tr><th>指数</th><th>PE变化</th><th>EPS变化</th><th>条件点位</th></tr></thead><tbody>
                <template v-for="v in report.valuation" :key="v.index_name"><tr v-for="stress in v.stress" :key="`${stress.pe_change_pct}-${stress.eps_change_pct}`"><th>{{ v.index_name }}</th><td>{{ stress.pe_change_pct }}%</td><td>{{ stress.eps_change_pct }}%</td><td>{{ number(stress.value) }}</td></tr></template>
              </tbody></table></div>
            </template>
            <template v-if="section.id === 'dollar'">
              <div class="table-scroll"><table><caption>全球市场：不同来源日期不合并成“今日”</caption><thead><tr><th>市场/资产</th><th>原值</th><th>近10观测变化</th><th>近20观测变化</th><th>来源日</th></tr></thead><tbody>
                <tr v-for="g in report.global_markets" :key="g.asset_code"><th><a :href="g.source_url" target="_blank" rel="noopener noreferrer">{{ g.name }}</a></th><td>{{ g.asset_code === 'COPPER_HG' ? '仅比较同序列变动' : number(g.value) }}</td><td>{{ percent(g.change_10obs_pct) }}</td><td>{{ percent(g.change_20obs_pct) }}</td><td>{{ g.source_date }}<small>{{ g.source }}</small></td></tr>
              </tbody></table></div>
            </template>
            <template v-if="section.id === 'fx'">
              <div class="table-scroll"><table><caption>外汇盘中快照，不冒充官方日收盘</caption><thead><tr><th>指标</th><th>原值</th><th>近20观测变化</th><th>来源日</th></tr></thead><tbody><tr v-for="fx in report.fx" :key="fx.code"><th>{{ fx.name }}</th><td>{{ number(fx.value, 4) }}</td><td>{{ percent(fx.change_20obs_pct) }}</td><td>{{ fx.source_date }}</td></tr></tbody></table></div>
            </template>
            <template v-if="section.id === 'commodities'">
              <div class="table-scroll"><table><caption>上金所官方人民币合约（非美元现货或基准价）</caption><thead><tr><th>合约</th><th>收盘</th><th>单位</th><th>交易日</th></tr></thead><tbody><tr v-for="metal in report.precious_metals" :key="metal.contract"><th><a :href="metal.source_url" target="_blank" rel="noopener noreferrer">{{ metal.contract }}</a></th><td>{{ number(metal.value) }}</td><td>{{ metal.unit === 'CNY/g' ? '元/克' : '元/千克' }}</td><td>{{ metal.date }}</td></tr></tbody></table></div>
            </template>
            <template v-if="section.id === 'limits'">
              <p class="muted">当前历史样本：{{ selected.index_name }}。{{ selected.historical_breaks.method }}</p>
              <div class="table-scroll"><table><thead><tr><th>后续窗口</th><th>完整样本</th><th>最低价变化中位</th><th>Q25 / Q75</th><th>期末涨跌中位</th><th>最低价低逾10%</th></tr></thead><tbody>
                <tr v-for="h in selected.historical_breaks.summaries" :key="h.window"><th>{{ h.window }}交易日</th><td>{{ h.sample_count }}</td><td>{{ percent(h.worst_median_pct) }}</td><td>{{ percent(h.worst_q25_pct) }} / {{ percent(h.worst_q75_pct) }}</td><td>{{ percent(h.return_median_pct) }}</td><td>{{ h.loss_over_10pct_count }}</td></tr>
              </tbody></table></div>
              <details><summary>全部事件与未完成窗口</summary><div class="table-scroll"><table><thead><tr><th>事件日</th><th>收盘</th><th>20日最低价变化</th><th>60日最低价变化</th><th>120日最低价变化</th></tr></thead><tbody>
                <tr v-for="event in selected.historical_breaks.events" :key="event.date"><th>{{ event.date }}</th><td>{{ number(event.close) }}</td><td>{{ percent(event.worst_20d_pct) }}</td><td>{{ percent(event.worst_60d_pct) }}</td><td>{{ percent(event.worst_120d_pct) }}</td></tr>
              </tbody></table></div></details>
            </template>
          </section>
          <section id="outlook-watchlist" class="research-section">
            <h4>条件检查清单</h4><p class="muted">用于更新研究结论，不是新策略，也未连接停买或通知。</p>
            <div class="table-scroll"><table><thead><tr><th>模块</th><th>当前基线</th><th>改善证据</th><th>恶化证据</th></tr></thead><tbody><tr v-for="w in report.watchlist" :key="w.topic"><th>{{ w.topic }}</th><td>{{ w.baseline }}</td><td>{{ w.improves }}</td><td>{{ w.worsens }}</td></tr></tbody></table></div>
          </section>
          <section id="outlook-sources" class="research-section">
            <h4>来源与数据边界</h4><ul class="quality-list"><li v-for="q in report.quality" :key="q">{{ q }}</li></ul>
            <details><summary>{{ report.sources.length }}个来源、发布日期与口径说明</summary><div class="source-list"><div v-for="source in report.sources" :key="source.id"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a><span>{{ dateTime(source.published_at) }}</span><p>{{ source.note }}</p></div></div></details>
            <details><summary>复算方法与证据指纹</summary><ul><li v-for="m in report.methods" :key="m">{{ m }}</li></ul><p class="fingerprint">数据库快照 SHA256 {{ report.provenance.snapshot_sha256 }}</p><p class="fingerprint">外部快照 SHA256 {{ report.provenance.external_sha256 }}</p><p v-if="report.provenance.history_snapshot_sha256" class="fingerprint">历史补充快照 SHA256 {{ report.provenance.history_snapshot_sha256 }}</p><p>版本 {{ report.version }} · 未写入生产数据</p></details>
          </section>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.outlook-research { min-width: 0; padding: 8px 2px 28px; color: #334155; }
.report-head, .section-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
h3 { margin: 0 0 8px; font-size: 21px; font-weight: 650; }
h4 { margin: 0 0 12px; font-size: 17px; }
.report-head p { margin: 0; font-size: 12px; }
.version { color: #64748b; font-size: 12px; }
.summary-band { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 22px 0 12px; border-top: 2px solid #2563eb; border-bottom: 1px solid #dbe3ec; background: #f3f7fc; }
.summary-band > div { padding: 15px 18px; }
.summary-band span { display: block; color: #64748b; font-size: 12px; margin-bottom: 6px; }
.summary-band strong { font-size: 16px; color: #1e3a8a; line-height: 1.6; }
.summary-band p { font-size: 13px; line-height: 1.7; margin: 7px 0 0; }
.quality-notice { border-left: 3px solid #d97706; padding: 7px 12px; font-size: 12px; line-height: 1.7; color: #92400e; }
.chart-band { padding: 20px 0; border-bottom: 1px solid #dbe3ec; }
.index-switch { display: inline-flex; flex-wrap: wrap; gap: 3px; padding: 3px; background: #eaf0f7; border-radius: 5px; }
.index-switch button { border: 0; padding: 7px 11px; border-radius: 3px; background: transparent; color: #475569; font: inherit; font-size: 12px; cursor: pointer; }
.index-switch button.active { background: #fff; color: #1d4ed8; box-shadow: 0 1px 3px #cbd5e1; }
.index-switch button:focus-visible, a:focus-visible, summary:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
.chart-facts { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 9px 0; font-size: 12px; font-variant-numeric: tabular-nums; }
.table-scroll { max-width: 100%; overflow-x: auto; margin: 14px 0 20px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; font-variant-numeric: tabular-nums; }
caption { text-align: left; color: #475569; font-weight: 600; margin: 8px 0; }
th, td { padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; line-height: 1.65; }
thead th { background: #f1f5f9; white-space: nowrap; color: #475569; }
tbody th { font-weight: 500; }
td { min-width: 65px; }
td small, th small { display: block; color: #64748b; font-weight: 400; }
.stress-row { color: #92400e; }
.reading-layout { display: grid; grid-template-columns: 208px minmax(0, 1fr); gap: 30px; margin-top: 22px; align-items: start; }
.contents { position: sticky; top: 90px; display: flex; flex-direction: column; gap: 3px; max-height: calc(100vh - 115px); overflow-y: auto; border-right: 1px solid #dbe3ec; padding-right: 12px; }
.contents a { padding: 7px 4px; font-size: 12px; line-height: 1.6; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
.report-body { min-width: 0; }
.research-section { padding: 10px 0 26px; margin-bottom: 20px; border-bottom: 1px solid #dbe3ec; scroll-margin-top: 90px; }
.verdict { color: #1e3a8a; font-size: 14px; font-weight: 600; line-height: 1.8; margin: 0 0 16px; }
.research-paragraph { font-size: 14px; line-height: 1.95; margin: 0 0 17px; }
.kind { margin-right: 8px; font-size: 11px; color: #64748b; border-bottom: 1px solid #94a3b8; }
.kind.hypothesis { color: #b45309; border-color: #d97706; }
.citations { display: block; margin-top: 5px; font-size: 11px; line-height: 1.7; }
.citations a { display: inline-block; margin-right: 12px; }
summary { font-size: 13px; color: #1d4ed8; cursor: pointer; padding: 12px 0; }
.quality-list, details ul { padding-left: 20px; font-size: 13px; line-height: 1.9; }
.source-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; padding: 12px 0; font-size: 12px; }
.source-list span { display: block; color: #64748b; margin-top: 5px; }
.source-list p { line-height: 1.7; margin: 5px 0 0; }
.fingerprint { font-size: 11px; color: #64748b; overflow-wrap: anywhere; }
.state { padding: 28px 0; } .error { color: #b91c1c; }
@media (max-width: 1350px) { .reading-layout { grid-template-columns: 180px minmax(0, 1fr); gap: 20px; } .summary-band > div { padding: 12px; } .summary-band strong { font-size: 14px; } }
@media (max-width: 1050px) { .reading-layout { display: block; } .contents { position: static; max-height: none; display: flex; flex-direction: row; flex-wrap: wrap; border: 0; border-bottom: 1px solid #dbe3ec; padding: 0 0 15px; margin-bottom: 24px; gap: 4px 16px; } .contents a { max-width: 100%; } }
@media (max-width: 700px) { .summary-band { grid-template-columns: 1fr; } .summary-band > div + div { border-top: 1px solid #dbe3ec; } h3 { font-size: 18px; } .source-list { grid-template-columns: 1fr; } table { min-width: 550px; } .research-paragraph { font-size: 13px; } }
</style>
