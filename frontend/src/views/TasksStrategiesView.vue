<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchRootVisibleStrategies } from '../api/tasks'
import { useAuthStore } from '../stores/auth'
import type { RootVisibleStrategy, RootVisibleStrategyTypeFilter } from '../types/tasks'

function extractErrorMessage(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null) {
    const candidate = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

const authStore = useAuthStore()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const strategies = ref<RootVisibleStrategy[]>([])

const keyword = ref('')
const username = ref('')
const strategyType = ref<RootVisibleStrategyTypeFilter>('stock')

const canView = computed(() => authStore.isRoot)

function ownerDisplay(item: RootVisibleStrategy) {
  return item.owner_nickname.trim() || item.owner_username
}

function strategyTypeLabel(strategyType: RootVisibleStrategy['strategy_type']) {
  if (strategyType === 'index') return '指数'
  if (strategyType === 'etf') return 'ETF'
  return '股票'
}

async function loadStrategies() {
  if (!canView.value) {
    strategies.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    strategies.value = await fetchRootVisibleStrategies({
      keyword: keyword.value.trim() || undefined,
      username: username.value.trim() || undefined,
      strategy_type: strategyType.value,
    })
  } catch (loadError) {
    error.value = extractErrorMessage(loadError, '全部策略加载失败')
  } finally {
    loading.value = false
  }
}

async function resetFilters() {
  keyword.value = ''
  username.value = ''
  strategyType.value = 'stock'
  await loadStrategies()
}

function applyToCollection(item: RootVisibleStrategy) {
  const sourceUsername = ownerDisplay(item)
  void router.push({
    path: '/tasks/manage',
    query: {
      task_type: 'collection',
      stock_code: item.target_code,
      stock_name: item.target_name,
      source_strategy_id: String(item.id),
      source_strategy_name: item.name,
      source_username: sourceUsername,
    },
  })
}

onMounted(async () => {
  await authStore.ensureInitialized()
  if (!canView.value) return
  await loadStrategies()
})
</script>

<template>
  <section class="card task-strategy-browser-card">
    <div class="progress-section-head">
      <div class="progress-section-copy">
        <h3>全部策略</h3>
        <p class="muted">这里只展示普通用户的策略，方便 root 从策略反推股票并快速预填采集任务。</p>
      </div>
    </div>

    <template v-if="canView">
      <div class="task-strategy-browser-filters">
        <label class="quant-field">
          <span class="quant-field-label">关键词</span>
          <input
            v-model="keyword"
            class="input"
            placeholder="策略名、股票代码、股票名称"
            @keydown.enter.prevent="loadStrategies()"
          />
        </label>

        <label class="quant-field">
          <span class="quant-field-label">用户筛选</span>
          <input
            v-model="username"
            class="input"
            placeholder="用户名或昵称"
            @keydown.enter.prevent="loadStrategies()"
          />
        </label>

        <label class="quant-field">
          <span class="quant-field-label">策略类型</span>
          <select v-model="strategyType" class="input">
            <option value="stock">股票策略</option>
            <option value="index">指数策略</option>
            <option value="etf">ETF 策略</option>
            <option value="all">全部类型</option>
          </select>
        </label>

        <div class="compact-toolbar-end">
          <button class="btn" type="button" @click="resetFilters()">重置筛选</button>
          <button class="btn primary" type="button" @click="loadStrategies()">查询策略</button>
        </div>
      </div>

      <p v-if="error" class="banner-error">{{ error }}</p>

      <p v-if="loading" class="muted">全部策略加载中...</p>
      <div v-else-if="strategies.length" class="task-strategy-browser-table-wrap">
        <table class="task-strategy-browser-table">
          <thead>
            <tr>
              <th>策略名</th>
              <th>用户</th>
              <th>类型</th>
              <th>标的代码</th>
              <th>标的名称</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in strategies" :key="item.id">
              <td>
                <div class="task-strategy-browser-primary">
                  <strong>{{ item.name }}</strong>
                  <span v-if="item.notes" class="muted">{{ item.notes }}</span>
                </div>
              </td>
              <td>
                <div class="task-strategy-browser-primary">
                  <strong>{{ ownerDisplay(item) }}</strong>
                  <span class="muted">{{ item.owner_username }}</span>
                </div>
              </td>
              <td>{{ strategyTypeLabel(item.strategy_type) }}</td>
              <td>{{ item.target_code }}</td>
              <td>{{ item.target_name }}</td>
              <td>{{ item.updated_at ? item.updated_at.slice(0, 16).replace('T', ' ') : '-' }}</td>
              <td>
                <button
                  class="btn"
                  type="button"
                  :disabled="item.strategy_type !== 'stock'"
                  @click="applyToCollection(item)"
                >
                  用于采集
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="muted">当前条件下没有匹配的普通用户策略。</p>
    </template>

    <template v-else>
      <div class="quant-stock-empty">
        <h3>无访问权限</h3>
        <p class="muted">这个页面仅对 root 用户开放，用于为采集任务挑选来自普通用户策略的股票。</p>
      </div>
    </template>
  </section>
</template>
