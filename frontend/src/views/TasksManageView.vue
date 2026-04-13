<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { createTask, deleteTask, fetchTaskRuns, fetchTasks, runTaskNow, toggleTask, updateTask } from '../api/tasks'
import { fetchQuantStrategies, fetchSymbols } from '../api/stocks'
import { useAuthStore } from '../stores/auth'
import type { QuantStrategyConfig } from '../types/quant'
import type { StockSymbol } from '../types/stock'
import type { ScheduledTask, ScheduledTaskRun, ScheduledTaskType, TaskMarketScope, TaskPayload } from '../types/tasks'

type TaskDraft = {
  name: string
  task_type: ScheduledTaskType
  market_scope: TaskMarketScope
  schedule_time: string
  enabled: boolean
  stock_code: string
  strategy_ids: number[]
}

type SourceStrategyInfo = {
  id: number | null
  name: string
  username: string
}

let collectionSearchTimer: number | null = null

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

function cloneTaskToDraft(task: ScheduledTask): TaskDraft {
  return {
    name: task.name,
    task_type: task.task_type,
    market_scope: task.market_scope,
    schedule_time: task.schedule_time,
    enabled: task.enabled,
    stock_code: task.stock_code ?? '',
    strategy_ids: [...task.strategy_ids],
  }
}

function createDefaultDraft(taskType: ScheduledTaskType): TaskDraft {
  return {
    name: '',
    task_type: taskType,
    market_scope: 'cn_stock',
    schedule_time: '09:00',
    enabled: true,
    stock_code: '',
    strategy_ids: [],
  }
}

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const tasks = ref<ScheduledTask[]>([])
const strategyOptions = ref<QuantStrategyConfig[]>([])
const selectedTaskId = ref<number | null>(null)
const runs = ref<ScheduledTaskRun[]>([])
const loading = ref(false)
const runsLoading = ref(false)
const saving = ref(false)
const actionLoading = ref(false)
const error = ref('')
const message = ref('')
const isCreating = ref(false)
const sourceStrategy = ref<SourceStrategyInfo | null>(null)
const draft = reactive<TaskDraft>(createDefaultDraft('notification'))

const collectionKeyword = ref('')
const selectedCollectionName = ref('')
const showCollectionSuggestions = ref(false)
const collectionSuggestionLoading = ref(false)
const collectionSuggestions = ref<StockSymbol[]>([])

const currentTask = computed(() => tasks.value.find((item) => item.id === selectedTaskId.value) ?? null)
const canCreateCollection = computed(() => authStore.isRoot)
const canCreateNotification = computed(() => authStore.isAuthenticated && !authStore.isGuest)
const targetEmail = computed(() => authStore.user?.email ?? null)

const formTitle = computed(() => {
  if (isCreating.value) {
    return draft.task_type === 'collection' ? '新建采集任务' : '新建通知任务'
  }
  return currentTask.value ? `编辑任务：${currentTask.value.name}` : '任务详情'
})

const canSave = computed(() => {
  if (!draft.name.trim() || !draft.schedule_time.trim()) return false
  if (draft.task_type === 'collection') {
    return canCreateCollection.value && Boolean(draft.stock_code.trim())
  }
  return canCreateNotification.value && Boolean(targetEmail.value) && draft.strategy_ids.length > 0
})

function resetCollectionPicker() {
  collectionKeyword.value = ''
  selectedCollectionName.value = ''
  showCollectionSuggestions.value = false
  collectionSuggestions.value = []
  collectionSuggestionLoading.value = false
}

function clearSourceStrategy() {
  sourceStrategy.value = null
}

function applyDraftTask(taskType: ScheduledTaskType) {
  if (taskType === 'collection') {
    draft.strategy_ids = []
    return
  }
  draft.stock_code = ''
  resetCollectionPicker()
  clearSourceStrategy()
}

function toPayload(): TaskPayload {
  return {
    name: draft.name.trim(),
    task_type: draft.task_type,
    market_scope: draft.market_scope,
    schedule_time: draft.schedule_time,
    enabled: draft.enabled,
    stock_code: draft.task_type === 'collection' ? draft.stock_code.trim() || null : null,
    strategy_ids: draft.task_type === 'notification' ? draft.strategy_ids : [],
  }
}

async function syncCollectionPickerFromCode(stockCode: string, stockName?: string | null) {
  const normalizedCode = stockCode.trim()
  draft.stock_code = normalizedCode
  collectionKeyword.value = normalizedCode
  selectedCollectionName.value = stockName?.trim() || ''
  if (!normalizedCode || selectedCollectionName.value) {
    return
  }
  try {
    const items = await fetchSymbols(20, normalizedCode)
    const exactMatch = items.find((item) => item.ts_code === normalizedCode)
    if (exactMatch) {
      selectedCollectionName.value = exactMatch.stock_name
    }
  } catch {
    // Keep the stock code visible even if the name lookup fails.
  }
}

function resetForCreate(taskType: ScheduledTaskType, nextSourceStrategy: SourceStrategyInfo | null = null) {
  isCreating.value = true
  selectedTaskId.value = null
  runs.value = []
  Object.assign(draft, createDefaultDraft(taskType))
  resetCollectionPicker()
  sourceStrategy.value = nextSourceStrategy
  message.value = ''
  error.value = ''
}

async function loadRuns(taskId: number) {
  runsLoading.value = true
  try {
    runs.value = await fetchTaskRuns(taskId)
  } catch (loadError) {
    error.value = extractErrorMessage(loadError, '执行记录加载失败')
  } finally {
    runsLoading.value = false
  }
}

async function selectTask(taskId: number) {
  const target = tasks.value.find((item) => item.id === taskId)
  if (!target) return
  isCreating.value = false
  selectedTaskId.value = taskId
  clearSourceStrategy()
  Object.assign(draft, cloneTaskToDraft(target))
  applyDraftTask(draft.task_type)
  if (draft.task_type === 'collection') {
    await syncCollectionPickerFromCode(draft.stock_code, target.stock_name)
  }
  message.value = ''
  error.value = ''
  await loadRuns(taskId)
}

async function loadTasks(preferredTaskId?: number | null, preserveCreateState = false) {
  loading.value = true
  try {
    tasks.value = await fetchTasks()
    if (preserveCreateState) {
      selectedTaskId.value = null
      runs.value = []
      return
    }

    const nextId = preferredTaskId ?? selectedTaskId.value ?? tasks.value[0]?.id ?? null
    if (nextId && tasks.value.some((item) => item.id === nextId)) {
      await selectTask(nextId)
    } else {
      selectedTaskId.value = null
      runs.value = []
      if (!isCreating.value) {
        Object.assign(draft, createDefaultDraft(canCreateCollection.value ? 'collection' : 'notification'))
        resetCollectionPicker()
        clearSourceStrategy()
      }
    }
  } catch (loadError) {
    error.value = extractErrorMessage(loadError, '任务列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadStrategyOptions() {
  if (!canCreateNotification.value) {
    strategyOptions.value = []
    return
  }
  try {
    strategyOptions.value = await fetchQuantStrategies()
  } catch (loadError) {
    error.value = extractErrorMessage(loadError, '策略列表加载失败')
  }
}

async function loadCollectionSuggestions(keyword: string) {
  const trimmed = keyword.trim()
  if (!trimmed) {
    collectionSuggestions.value = []
    collectionSuggestionLoading.value = false
    return
  }
  collectionSuggestionLoading.value = true
  try {
    collectionSuggestions.value = await fetchSymbols(12, trimmed)
  } catch {
    collectionSuggestions.value = []
  } finally {
    collectionSuggestionLoading.value = false
  }
}

function scheduleCollectionSearch(keyword: string) {
  if (collectionSearchTimer) {
    window.clearTimeout(collectionSearchTimer)
  }
  collectionSearchTimer = window.setTimeout(() => {
    void loadCollectionSuggestions(keyword)
  }, 280)
}

function handleCollectionInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  collectionKeyword.value = value
  draft.stock_code = value.trim()
  selectedCollectionName.value = ''
  showCollectionSuggestions.value = Boolean(value.trim())
  scheduleCollectionSearch(value)
}

function pickCollectionSymbol(symbol: StockSymbol) {
  draft.stock_code = symbol.ts_code
  collectionKeyword.value = symbol.ts_code
  selectedCollectionName.value = symbol.stock_name
  collectionSuggestions.value = []
  showCollectionSuggestions.value = false
}

function handleCollectionBlur() {
  window.setTimeout(() => {
    showCollectionSuggestions.value = false
  }, 120)
}

async function applyRoutePrefill() {
  const taskType = typeof route.query.task_type === 'string' ? route.query.task_type : ''
  const stockCode = typeof route.query.stock_code === 'string' ? route.query.stock_code.trim() : ''
  if (taskType !== 'collection' || !stockCode || !canCreateCollection.value) {
    return false
  }

  const sourceStrategyIdRaw = typeof route.query.source_strategy_id === 'string' ? route.query.source_strategy_id : ''
  const sourceStrategyId = /^\d+$/.test(sourceStrategyIdRaw) ? Number(sourceStrategyIdRaw) : null
  const sourceStrategyName =
    typeof route.query.source_strategy_name === 'string' ? route.query.source_strategy_name.trim() : ''
  const sourceUsername = typeof route.query.source_username === 'string' ? route.query.source_username.trim() : ''
  const stockName = typeof route.query.stock_name === 'string' ? route.query.stock_name : ''

  resetForCreate('collection', {
    id: sourceStrategyId,
    name: sourceStrategyName,
    username: sourceUsername,
  })
  await syncCollectionPickerFromCode(stockCode, stockName)

  const nextQuery = { ...route.query }
  delete nextQuery.task_type
  delete nextQuery.stock_code
  delete nextQuery.stock_name
  delete nextQuery.source_strategy_id
  delete nextQuery.source_strategy_name
  delete nextQuery.source_username
  await router.replace({ path: route.path, query: nextQuery })
  return true
}

async function saveTask() {
  if (!canSave.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = toPayload()
    const saved =
      isCreating.value || !selectedTaskId.value
        ? await createTask(payload)
        : await updateTask(selectedTaskId.value, payload)
    message.value = isCreating.value || !selectedTaskId.value ? `任务已创建：${saved.name}` : `任务已更新：${saved.name}`
    isCreating.value = false
    clearSourceStrategy()
    await loadTasks(saved.id)
  } catch (saveError) {
    error.value = extractErrorMessage(saveError, '任务保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleCurrentTask() {
  if (!currentTask.value) return
  actionLoading.value = true
  error.value = ''
  message.value = ''
  try {
    const updated = await toggleTask(currentTask.value.id, !currentTask.value.enabled)
    message.value = updated.enabled ? `任务已启用：${updated.name}` : `任务已停用：${updated.name}`
    await loadTasks(updated.id)
  } catch (toggleError) {
    error.value = extractErrorMessage(toggleError, '任务状态更新失败')
  } finally {
    actionLoading.value = false
  }
}

async function runCurrentTask() {
  if (!currentTask.value) return
  actionLoading.value = true
  error.value = ''
  message.value = ''
  try {
    await runTaskNow(currentTask.value.id)
    message.value = `任务已提交执行：${currentTask.value.name}`
    await loadRuns(currentTask.value.id)
    await loadTasks(currentTask.value.id)
  } catch (runError) {
    error.value = extractErrorMessage(runError, '任务立即执行失败')
  } finally {
    actionLoading.value = false
  }
}

async function removeCurrentTask() {
  if (!currentTask.value) return
  actionLoading.value = true
  error.value = ''
  message.value = ''
  try {
    const deletingId = currentTask.value.id
    await deleteTask(deletingId)
    message.value = '任务已删除'
    selectedTaskId.value = null
    runs.value = []
    clearSourceStrategy()
    await loadTasks(tasks.value.find((item) => item.id !== deletingId)?.id ?? null)
  } catch (deleteError) {
    error.value = extractErrorMessage(deleteError, '任务删除失败')
  } finally {
    actionLoading.value = false
  }
}

watch(
  () => draft.task_type,
  (taskType) => {
    applyDraftTask(taskType)
  },
)

watch(
  () => [
    route.query.task_type,
    route.query.stock_code,
    route.query.stock_name,
    route.query.source_strategy_id,
    route.query.source_strategy_name,
    route.query.source_username,
  ],
  async () => {
    if (!authStore.isAuthenticated) return
    await applyRoutePrefill()
  },
)

onMounted(async () => {
  await authStore.ensureInitialized()
  if (!authStore.isAuthenticated) return
  if (!authStore.isGuest) {
    await loadStrategyOptions()
  }
  const hasPrefill = await applyRoutePrefill()
  await loadTasks(null, hasPrefill)
  if (!tasks.value.length && canCreateNotification.value && !hasPrefill) {
    resetForCreate(canCreateCollection.value ? 'collection' : 'notification')
  }
})

onUnmounted(() => {
  if (collectionSearchTimer) {
    window.clearTimeout(collectionSearchTimer)
  }
})
</script>

<template>
  <section class="tasks-grid">
    <section class="card task-list-card">
      <div class="progress-section-head">
        <div class="progress-section-copy">
          <h3>我的任务</h3>
          <p class="muted">任务按当前登录用户隔离；仅 root 可以创建采集任务。</p>
        </div>
        <div class="compact-toolbar">
          <button v-if="canCreateCollection" class="btn" @click="resetForCreate('collection')">新建采集任务</button>
          <button v-if="canCreateNotification" class="btn primary" @click="resetForCreate('notification')">
            新建通知任务
          </button>
        </div>
      </div>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-else-if="message" class="banner-success">{{ message }}</p>

      <p v-if="loading" class="muted">任务列表加载中...</p>
      <div v-else-if="tasks.length" class="timeline quant-strategy-list task-list">
        <button
          v-for="item in tasks"
          :key="item.id"
          type="button"
          class="sidebar-link quant-strategy-item"
          :class="{ active: selectedTaskId === item.id && !isCreating }"
          @click="selectTask(item.id)"
        >
          <strong>{{ item.name }}</strong>
          <span>{{ item.task_type === 'collection' ? '采集任务' : '通知任务' }} / {{ item.schedule_time }}</span>
          <span v-if="item.task_type === 'collection'">
            {{ item.stock_code }}<template v-if="item.stock_name"> / {{ item.stock_name }}</template>
          </span>
          <span v-else>{{ item.strategy_names.length }} 条策略 / {{ item.target_email || '未设置邮箱' }}</span>
          <span>{{ item.enabled ? '启用中' : '已停用' }} / {{ item.last_run_status || '尚未执行' }}</span>
        </button>
      </div>
      <p v-else class="muted">
        {{ authStore.isGuest ? '游客账号当前没有可管理的任务。' : '当前还没有任务，先在右上角创建一条吧。' }}
      </p>
    </section>

    <section class="card task-detail-card">
      <template v-if="isCreating || currentTask">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>{{ formTitle }}</h3>
            <p class="muted">
              <template v-if="draft.task_type === 'collection'">
                每天到点会自动触发一次后复权采集，一条任务只负责一只股票。
              </template>
              <template v-else>
                每天到点会给当前账户邮箱发送一封策略汇总邮件，即使没有红蓝信号也会写“无操作”。
              </template>
            </p>
          </div>
          <span v-if="currentTask && !isCreating" class="account-readonly-tag">
            {{ currentTask.enabled ? '启用中' : '已停用' }}
          </span>
        </div>

        <div class="quant-strategy-form">
          <label class="quant-field">
            <span class="quant-field-label">任务名称</span>
            <input v-model="draft.name" class="input" placeholder="例如：每日 600519 后复权采集" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">任务类型</span>
            <select v-model="draft.task_type" class="input" :disabled="!isCreating">
              <option v-if="canCreateCollection" value="collection">采集任务</option>
              <option v-if="canCreateNotification" value="notification">通知任务</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">执行时间</span>
            <input v-model="draft.schedule_time" class="input" type="time" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">启用状态</span>
            <select v-model="draft.enabled" class="input">
              <option :value="true">启用</option>
              <option :value="false">停用</option>
            </select>
          </label>
        </div>

        <div v-if="draft.task_type === 'collection'" class="task-form-section">
          <div v-if="sourceStrategy" class="task-source-banner">
            <strong>来源策略</strong>
            <span>来自 {{ sourceStrategy.username }} / {{ sourceStrategy.name }}</span>
          </div>

          <label class="quant-field">
            <span class="quant-field-label">采集股票</span>
            <div class="search-wrap">
              <input
                :value="collectionKeyword"
                class="input"
                placeholder="输入股票代码或名称后选择"
                @focus="showCollectionSuggestions = Boolean(collectionKeyword.trim())"
                @input="handleCollectionInput"
                @blur="handleCollectionBlur"
              />
              <ul v-if="showCollectionSuggestions" class="suggest-list task-suggest-list">
                <li v-if="collectionSuggestionLoading">
                  <span>搜索中...</span>
                </li>
                <li v-else-if="!collectionSuggestions.length">
                  <span>没有匹配结果</span>
                </li>
                <template v-else>
                  <li
                    v-for="item in collectionSuggestions"
                    :key="item.ts_code"
                    @mousedown.prevent="pickCollectionSymbol(item)"
                  >
                    <span>{{ item.ts_code }}</span>
                    <strong>{{ item.stock_name }}</strong>
                  </li>
                </template>
              </ul>
            </div>
          </label>

          <div v-if="draft.stock_code" class="task-stock-pill">
            <strong>{{ draft.stock_code }}</strong>
            <span>{{ selectedCollectionName || '未匹配到股票名称' }}</span>
          </div>
        </div>

        <div v-else class="task-form-section">
          <div class="task-email-banner" :class="{ warn: !targetEmail }">
            <strong>当前通知邮箱：</strong>
            <span>{{ targetEmail || '未设置，请先到个人中心补充邮箱' }}</span>
          </div>

          <div class="task-strategy-picker">
            <p class="muted">选择需要纳入每日通知的策略：</p>
            <div v-if="strategyOptions.length" class="task-strategy-checklist">
              <label v-for="strategy in strategyOptions" :key="strategy.id" class="task-strategy-option">
                <input v-model="draft.strategy_ids" type="checkbox" :value="strategy.id" />
                <span>{{ strategy.name }} / {{ strategy.target_name }}</span>
              </label>
            </div>
            <p v-else class="muted">当前账户还没有已保存策略，先去“策略回测”保存策略后再创建通知任务。</p>
          </div>
        </div>

        <div class="progress-hero-actions">
          <button class="btn primary" :disabled="saving || !canSave" @click="saveTask()">
            {{ saving ? '保存中...' : isCreating ? '创建任务' : '保存修改' }}
          </button>
          <button v-if="currentTask && !isCreating" class="btn" :disabled="actionLoading" @click="toggleCurrentTask()">
            {{ currentTask.enabled ? '停用任务' : '启用任务' }}
          </button>
          <button v-if="currentTask && !isCreating" class="btn" :disabled="actionLoading" @click="runCurrentTask()">
            立即执行
          </button>
          <button v-if="currentTask && !isCreating" class="btn" :disabled="actionLoading" @click="removeCurrentTask()">
            删除任务
          </button>
        </div>

        <section v-if="currentTask && !isCreating" class="task-runs-panel">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>最近执行记录</h3>
              <p class="muted">查看任务最近一次触发、完成状态以及失败原因。</p>
            </div>
          </div>

          <p v-if="runsLoading" class="muted">执行记录加载中...</p>
          <div v-else-if="runs.length" class="timeline">
            <article v-for="run in runs" :key="run.id" class="timeline-item">
              <div class="timeline-date">{{ run.scheduled_for?.slice(0, 16).replace('T', ' ') || '-' }}</div>
              <div class="timeline-body">
                <h4>{{ run.trigger_type === 'manual' ? '手动执行' : '定时执行' }} / {{ run.status }}</h4>
                <p class="muted">{{ run.summary || run.error_message || '暂无摘要信息' }}</p>
              </div>
            </article>
          </div>
          <p v-else class="muted">这条任务暂时还没有执行记录。</p>
        </section>
      </template>

      <template v-else>
        <div class="quant-stock-empty">
          <h3>任务详情</h3>
          <p class="muted">从左侧选择一条任务，或者先新建一条采集任务 / 通知任务。</p>
        </div>
      </template>
    </section>
  </section>
</template>
