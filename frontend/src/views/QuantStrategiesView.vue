<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  deleteQuantStrategy,
  fetchQuantStrategies,
  fetchQuantStrategyEquityCurve,
  updateQuantStrategy,
} from '../api/stocks'
import StrategyEquityCurveChart from '../components/StrategyEquityCurveChart.vue'
import type {
  QuantConflictMode,
  QuantEquityCurveResponse,
  QuantExecutionPriceMode,
  QuantSignalColor,
  QuantStrategyConfig,
  QuantStrategyPayload,
} from '../types/quant'

const strategies = ref<QuantStrategyConfig[]>([])
const selectedStrategyId = ref<number | null>(null)
const editingStrategy = ref<QuantStrategyConfig | null>(null)
const equityCurve = ref<QuantEquityCurveResponse | null>(null)
const loading = ref(false)
const curveLoading = ref(false)
const curveRequested = ref(false)
const error = ref('')
const saveMessage = ref('')

const signalColorOptions: Array<{ value: QuantSignalColor; label: string }> = [
  { value: 'blue', label: '蓝色' },
  { value: 'red', label: '红色' },
]

const conflictModeOptions: Array<{ value: QuantConflictMode; label: string }> = [
  { value: 'sell_first', label: '紫色优先卖出' },
  { value: 'buy_first', label: '紫色优先买入' },
  { value: 'skip', label: '紫色跳过' },
]

const executionModeOptions: Array<{ value: QuantExecutionPriceMode; label: string }> = [
  { value: 'next_open', label: '次日开盘价' },
  { value: 'next_close', label: '次日收盘价' },
  { value: 'next_best', label: '次日最优' },
]

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function cloneStrategy(strategy: QuantStrategyConfig): QuantStrategyConfig {
  return {
    ...strategy,
    notes: strategy.notes ?? '',
    indicator_params: cloneJson(strategy.indicator_params),
    blue_filter_groups: cloneJson(strategy.blue_filter_groups),
    red_filter_groups: cloneJson(strategy.red_filter_groups),
    blue_filters: cloneJson(strategy.blue_filters),
    red_filters: cloneJson(strategy.red_filters),
    blue_boll_filter: cloneJson(strategy.blue_boll_filter),
    red_boll_filter: cloneJson(strategy.red_boll_filter),
  }
}

function toPayload(strategy: QuantStrategyConfig): QuantStrategyPayload {
  return {
    name: strategy.name,
    notes: strategy.notes ?? '',
    strategy_type: strategy.strategy_type,
    target_code: strategy.target_code,
    target_name: strategy.target_name,
    indicator_params: strategy.indicator_params,
    blue_filter_groups: strategy.blue_filter_groups,
    red_filter_groups: strategy.red_filter_groups,
    blue_filters: strategy.blue_filters,
    red_filters: strategy.red_filters,
    blue_boll_filter: strategy.blue_boll_filter,
    red_boll_filter: strategy.red_boll_filter,
    signal_buy_color: strategy.signal_buy_color,
    signal_sell_color: strategy.signal_sell_color,
    purple_conflict_mode: strategy.purple_conflict_mode,
    start_date: strategy.start_date || null,
    buy_position_pct: strategy.buy_position_pct,
    sell_position_pct: strategy.sell_position_pct,
    execution_price_mode: strategy.execution_price_mode,
  }
}

async function loadStrategies(preferredId?: number | null) {
  loading.value = true
  error.value = ''
  try {
    strategies.value = await fetchQuantStrategies()
    const fallbackId = preferredId ?? selectedStrategyId.value ?? strategies.value[0]?.id ?? null
    if (fallbackId && strategies.value.some((item) => item.id === fallbackId)) {
      selectStrategy(fallbackId)
    } else {
      selectedStrategyId.value = null
      editingStrategy.value = null
      equityCurve.value = null
      curveRequested.value = false
    }
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '策略加载失败'
  } finally {
    loading.value = false
  }
}

async function loadEquityCurve(strategyId: number) {
  curveLoading.value = true
  error.value = ''
  try {
    equityCurve.value = await fetchQuantStrategyEquityCurve(strategyId)
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '收益曲线加载失败'
    equityCurve.value = null
  } finally {
    curveLoading.value = false
  }
}

function selectStrategy(strategyId: number) {
  const target = strategies.value.find((item) => item.id === strategyId)
  if (!target) return
  selectedStrategyId.value = strategyId
  editingStrategy.value = cloneStrategy(target)
  equityCurve.value = null
  curveRequested.value = false
  curveLoading.value = false
  saveMessage.value = ''
  error.value = ''
}

async function persistStrategy(showSavedMessage = true) {
  if (!editingStrategy.value) return null
  error.value = ''
  if (showSavedMessage) {
    saveMessage.value = ''
  }
  try {
    const updated = await updateQuantStrategy(editingStrategy.value.id, toPayload(editingStrategy.value))
    await loadStrategies(updated.id)
    if (showSavedMessage) {
      saveMessage.value = `已更新策略：${updated.name}`
    }
    return updated
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '策略保存失败'
    return null
  }
}

async function saveStrategy() {
  await persistStrategy(true)
}

async function confirmAndLoadCurve() {
  if (!editingStrategy.value) return
  saveMessage.value = ''
  const updated = await persistStrategy(false)
  if (!updated) return
  curveRequested.value = true
  await loadEquityCurve(updated.id)
}

async function removeStrategy() {
  if (!editingStrategy.value) return
  error.value = ''
  saveMessage.value = ''
  try {
    const deletingId = editingStrategy.value.id
    await deleteQuantStrategy(deletingId)
    await loadStrategies(strategies.value.find((item) => item.id !== deletingId)?.id ?? null)
    curveRequested.value = false
    saveMessage.value = '策略已删除'
  } catch (deleteError) {
    error.value = deleteError instanceof Error ? deleteError.message : '策略删除失败'
  }
}

onMounted(() => {
  void loadStrategies()
})
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>

  <div class="progress-grid quant-strategy-grid">
    <section class="card progress-card">
      <div class="progress-section-head">
        <div class="progress-section-copy">
          <h3>已保存策略</h3>
          <p class="muted">这里只加载策略列表；收益曲线会在你确认参数后单独计算。</p>
        </div>
      </div>

      <p v-if="loading" class="muted">策略列表加载中...</p>
      <div v-else-if="strategies.length" class="timeline quant-strategy-list">
        <button
          v-for="item in strategies"
          :key="item.id"
          type="button"
          class="sidebar-link quant-strategy-item"
          :class="{ active: selectedStrategyId === item.id }"
          @click="selectStrategy(item.id)"
        >
          <strong>{{ item.name }}</strong>
          <span>{{ item.strategy_type === 'index' ? '指数策略' : '股票策略' }} / {{ item.target_name }}</span>
          <span>{{ item.updated_at ? item.updated_at.slice(0, 10) : '暂无更新时间' }}</span>
        </button>
      </div>
      <p v-else class="muted">当前还没有已保存的策略，请先去指数或股票页面保存筛选条件。</p>
    </section>

    <section class="card progress-card progress-card-wide">
      <template v-if="editingStrategy">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>{{ editingStrategy.name }}</h3>
            <p class="muted">{{ editingStrategy.strategy_type === 'index' ? '指数策略' : '股票策略' }} / {{ editingStrategy.target_name }}</p>
          </div>
        </div>

        <div class="quant-strategy-form">
          <label class="quant-field">
            <span class="quant-field-label">策略名称</span>
            <input v-model="editingStrategy.name" class="input" />
          </label>
          <label class="quant-field quant-field-full">
            <span class="quant-field-label">策略备注</span>
            <textarea
              v-model="editingStrategy.notes"
              class="input progress-textarea progress-textarea-compact"
              placeholder="这里可以记录这条策略的思路、适用场景或注意事项。"
            />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">买入信号颜色</span>
            <select v-model="editingStrategy.signal_buy_color" class="input">
              <option v-for="option in signalColorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">卖出信号颜色</span>
            <select v-model="editingStrategy.signal_sell_color" class="input">
              <option v-for="option in signalColorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">紫色冲突处理</span>
            <select v-model="editingStrategy.purple_conflict_mode" class="input">
              <option v-for="option in conflictModeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">策略开始日期</span>
            <input v-model="editingStrategy.start_date" class="input" type="date" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">每次买入仓位</span>
            <input v-model.number="editingStrategy.buy_position_pct" class="input" type="number" min="0" step="0.01" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">每次卖出仓位</span>
            <input v-model.number="editingStrategy.sell_position_pct" class="input" type="number" min="0" step="0.01" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">成交价格模式</span>
            <select v-model="editingStrategy.execution_price_mode" class="input">
              <option v-for="option in executionModeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
        </div>

        <div class="progress-hero-actions">
          <button class="btn" @click="saveStrategy">保存策略</button>
          <button class="btn primary" :disabled="curveLoading" @click="confirmAndLoadCurve">确定并加载收益曲线</button>
          <button class="btn" @click="removeStrategy">删除策略</button>
        </div>

        <p v-if="saveMessage" class="muted">{{ saveMessage }}</p>

        <div v-if="equityCurve" class="summary quant-strategy-summary">
          <div>
            <div class="label">累计收益</div>
            <div class="value">{{ equityCurve.cumulative_return_pct.toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">年化收益</div>
            <div class="value">{{ equityCurve.annualized_return_pct.toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">最大回撤</div>
            <div class="value">{{ equityCurve.max_drawdown_pct.toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">回测交易日数</div>
            <div class="value">{{ equityCurve.points.length }}</div>
          </div>
          <div>
            <div class="label">当前执行价模式</div>
            <div class="value small">{{ editingStrategy.execution_price_mode }}</div>
          </div>
        </div>

        <p v-if="!curveRequested && !curveLoading" class="muted">
          当前只加载了策略配置。调整好选项后，点击“确定并加载收益曲线”再开始回测。
        </p>
        <StrategyEquityCurveChart v-else :points="equityCurve?.points ?? []" :loading="curveLoading" />
      </template>

      <template v-else>
        <div class="quant-stock-empty">
          <h3>策略回测</h3>
          <p class="muted">从左侧选择一个已保存策略后，这里会显示交易规则和收益曲线。</p>
        </div>
      </template>
    </section>
  </div>
</template>
