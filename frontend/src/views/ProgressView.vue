<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchProgressBoard, publishProgressBoard, updateProgressTodo } from '../api/progress'
import AppSidebar from '../components/AppSidebar.vue'
import { useAuthStore } from '../stores/auth'
import type {
  ProgressBoardResponse,
  ProgressDay,
  ProgressGenerationMeta,
  ProgressGenerationRepo,
  ProgressRepoLog,
  ProgressTodoItem,
} from '../types/progress'

const REPO_ORDER = ['FIT', 'AkShare Project']

function makeId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function cloneData<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function sortRepoLogs(repos: ProgressRepoLog[]) {
  return [...repos].sort((left, right) => {
    const leftIndex = REPO_ORDER.indexOf(left.repo_label)
    const rightIndex = REPO_ORDER.indexOf(right.repo_label)
    const leftOrder = leftIndex === -1 ? REPO_ORDER.length : leftIndex
    const rightOrder = rightIndex === -1 ? REPO_ORDER.length : rightIndex
    return leftOrder - rightOrder || left.repo_label.localeCompare(right.repo_label)
  })
}

function sortProgressDays(days: ProgressDay[]) {
  return [...days]
    .map((day) => ({
      ...day,
      repos: sortRepoLogs(day.repos ?? []),
    }))
    .sort((left, right) => right.date.localeCompare(left.date) || right.title.localeCompare(left.title))
}

function createTodo(text = ''): ProgressTodoItem {
  return {
    id: makeId(),
    text,
  }
}

function sanitizeTodoItems(items: ProgressTodoItem[]) {
  return items
    .map((item) => ({ ...item, text: item.text.trim() }))
    .filter((item) => item.text)
}

function formatDateTime(rawValue: string | null) {
  if (!rawValue) return '未记录'
  const value = new Date(rawValue)
  if (Number.isNaN(value.getTime())) return rawValue
  return value.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function shortRef(value: string | null) {
  if (!value) return '全历史'
  return value.length > 12 ? value.slice(0, 12) : value
}

function formatGenerationRepo(repo: ProgressGenerationRepo) {
  const base = repo.base_ref ? shortRef(repo.base_ref) : '全历史'
  return `${repo.repo_label}：${base} -> ${shortRef(repo.head_ref)}，共 ${repo.commit_count} 个提交`
}

function resolveRequestError(rawError: unknown, fallback: string) {
  const candidate = (rawError as { response?: { data?: { detail?: string } } }).response?.data?.detail
  if (candidate) return candidate
  return rawError instanceof Error ? rawError.message : fallback
}

function hasAnyUpdates(days: ProgressDay[]) {
  return days.some((day) => (day.repos ?? []).some((repo) => (repo.updates ?? []).length > 0))
}

const authStore = useAuthStore()

const todoItems = ref<ProgressTodoItem[]>([])
const draftTodoItems = ref<ProgressTodoItem[]>([])
const publishedProgressDays = ref<ProgressDay[]>([])
const draftProgressDays = ref<ProgressDay[]>([])
const publishedGenerationMeta = ref<ProgressGenerationMeta | null>(null)
const draftGenerationMeta = ref<ProgressGenerationMeta | null>(null)

const loading = ref(true)
const savingTodo = ref(false)
const publishing = ref(false)
const isEditingTodo = ref(false)
const error = ref('')
const successMessage = ref('')

const updatedAt = ref<string | null>(null)
const updatedByName = ref<string | null>(null)
const lastPublishedAt = ref<string | null>(null)
const lastPublishedByName = ref<string | null>(null)

const canManage = computed(() => authStore.isRoot)
const showPublishedMeta = computed(() => canManage.value)
const displayTodoItems = computed(() => sanitizeTodoItems(todoItems.value))
const displayPublishedProgressDays = computed(() => sortProgressDays(publishedProgressDays.value))
const displayDraftProgressDays = computed(() => sortProgressDays(draftProgressDays.value))
const hasDraftContent = computed(() => hasAnyUpdates(displayDraftProgressDays.value))
const publishedSectionTitle = computed(() => (canManage.value ? '已发布更新日志' : '更新日志'))

const pageHint = computed(() => {
  if (loading.value) return '正在加载开发进度与更新日志...'
  if (canManage.value) {
    return '开发日志由这条 Codex 专用对话生成并写入草稿；本页面只负责查看草稿、确认范围并发布。'
  }
  return '这里展示已发布的开发日志。'
})

const publishedMetaText = computed(() => {
  if (lastPublishedAt.value) {
    return `最近发布：${formatDateTime(lastPublishedAt.value)}${lastPublishedByName.value ? ` / ${lastPublishedByName.value}` : ''}`
  }
  return '还没有发布过开发日志。'
})

const todoMetaText = computed(() => {
  if (updatedAt.value) {
    return `最近更新：${formatDateTime(updatedAt.value)}${updatedByName.value ? ` / ${updatedByName.value}` : ''}`
  }
  return canManage.value ? 'TODO 由 root 单独维护。' : '这里展示当前共享 TODO。'
})

const draftMetaText = computed(() => {
  if (!canManage.value) return ''
  return '草稿内容由 Codex 对话直接生成并写入；这里仅用于审核内容和确认发布时间。'
})

const publishedGenerationCaption = computed(() => {
  if (!publishedGenerationMeta.value) {
    return '当前已发布内容还没有记录生成范围。'
  }
  return `最近一版由 ${publishedGenerationMeta.value.generator} 于 ${formatDateTime(publishedGenerationMeta.value.generated_at)} 生成，覆盖范围如下：`
})

const draftGenerationCaption = computed(() => {
  if (!draftGenerationMeta.value) {
    return '当前还没有记录草稿生成范围，请先在这条 Codex 专用对话里生成开发日志。'
  }
  return `当前草稿由 ${draftGenerationMeta.value.generator} 于 ${formatDateTime(draftGenerationMeta.value.generated_at)} 生成，覆盖范围如下：`
})

const publishedGenerationLines = computed(() => {
  return publishedGenerationMeta.value?.repos.map(formatGenerationRepo) ?? []
})

const draftGenerationLines = computed(() => {
  return draftGenerationMeta.value?.repos.map(formatGenerationRepo) ?? []
})

function applyBoard(board: ProgressBoardResponse) {
  todoItems.value = board.todo_items ?? []
  publishedProgressDays.value = sortProgressDays(board.published_progress_days ?? [])
  draftProgressDays.value = sortProgressDays(board.draft_progress_days ?? [])
  publishedGenerationMeta.value = board.published_generation_meta ?? null
  draftGenerationMeta.value = board.draft_generation_meta ?? null
  updatedAt.value = board.updated_at
  updatedByName.value = board.updated_by_name
  lastPublishedAt.value = board.last_published_at
  lastPublishedByName.value = board.last_published_by_name
}

async function loadBoard() {
  loading.value = true
  error.value = ''
  try {
    const board = await fetchProgressBoard()
    applyBoard(board)
  } catch (loadError) {
    error.value = resolveRequestError(loadError, '开发进度加载失败')
  } finally {
    loading.value = false
  }
}

function startTodoEditing() {
  draftTodoItems.value = cloneData(todoItems.value)
  successMessage.value = ''
  error.value = ''
  isEditingTodo.value = true
}

function cancelTodoEditing() {
  draftTodoItems.value = []
  isEditingTodo.value = false
}

async function saveTodo() {
  savingTodo.value = true
  error.value = ''
  successMessage.value = ''
  try {
    const board = await updateProgressTodo({ todo_items: sanitizeTodoItems(draftTodoItems.value) })
    applyBoard(board)
    isEditingTodo.value = false
    successMessage.value = 'TODO 已保存。'
  } catch (saveError) {
    error.value = resolveRequestError(saveError, 'TODO 保存失败')
  } finally {
    savingTodo.value = false
  }
}

async function handlePublish() {
  if (!hasDraftContent.value) {
    error.value = '当前没有可发布的开发日志草稿。'
    return
  }
  publishing.value = true
  error.value = ''
  successMessage.value = ''
  try {
    const board = await publishProgressBoard()
    applyBoard(board)
    successMessage.value = '开发日志已发布。'
  } catch (publishError) {
    error.value = resolveRequestError(publishError, '开发日志发布失败')
  } finally {
    publishing.value = false
  }
}

function addTodo() {
  draftTodoItems.value.unshift(createTodo(''))
}

function removeTodo(id: string) {
  draftTodoItems.value = draftTodoItems.value.filter((item) => item.id !== id)
}

onMounted(async () => {
  await authStore.ensureInitialized()
  await loadBoard()
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="progress" />

    <main class="dashboard-main progress-main">
      <section class="card progress-hero">
        <div>
          <p class="progress-kicker">Changelog</p>
          <h2>开发进度</h2>
          <p class="muted">{{ pageHint }}</p>
        </div>

        <div class="progress-hero-actions">
          <template v-if="canManage">
            <button class="btn secondary" :disabled="loading || publishing || !hasDraftContent" @click="handlePublish">
              {{ publishing ? '正在发布...' : '发布当前草稿' }}
            </button>
          </template>
          <span v-else class="account-readonly-tag">只读查看</span>
        </div>
      </section>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-else-if="successMessage" class="banner-success">{{ successMessage }}</p>

      <section class="progress-grid">
        <section class="card progress-card progress-todo-card">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>TODO</h3>
              <p class="muted">{{ todoMetaText }}</p>
            </div>
            <div class="progress-todo-actions">
              <template v-if="canManage && isEditingTodo">
                <button class="btn" @click="addTodo">新增 TODO</button>
              </template>
              <template v-else-if="canManage">
                <button class="btn" :disabled="loading" @click="startTodoEditing">编辑 TODO</button>
              </template>
            </div>
          </div>

          <p v-if="loading" class="muted">开发进度加载中...</p>
          <template v-else-if="canManage && isEditingTodo">
            <div class="editable-list">
              <article v-for="item in draftTodoItems" :key="item.id" class="editable-card editable-card-compact">
                <textarea
                  v-model="item.text"
                  class="input progress-textarea progress-textarea-compact"
                  rows="4"
                  placeholder="输入待办内容"
                />
                <button class="btn progress-row-action" @click="removeTodo(item.id)">删除</button>
              </article>
            </div>
            <div class="progress-inline-actions">
              <button class="btn primary" :disabled="savingTodo" @click="saveTodo">
                {{ savingTodo ? '正在保存 TODO...' : '保存 TODO' }}
              </button>
              <button class="btn" :disabled="savingTodo" @click="cancelTodoEditing">取消</button>
            </div>
          </template>
          <template v-else>
            <ul v-if="displayTodoItems.length" class="progress-list">
              <li v-for="item in displayTodoItems" :key="item.id">{{ item.text }}</li>
            </ul>
            <p v-else class="muted">当前还没有待办事项。</p>
          </template>
        </section>

        <section class="card progress-card progress-card-wide progress-published-card">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>{{ publishedSectionTitle }}</h3>
              <p v-if="showPublishedMeta" class="muted">
                按“日期 -> 仓库 -> 具体更新内容”展示，面向所有已登录用户只读开放。
              </p>
            </div>
            <div v-if="showPublishedMeta" class="progress-meta-panel">
              <span class="quant-scan-status tone-info">发布状态</span>
              <span class="muted">{{ publishedMetaText }}</span>
            </div>
          </div>

          <div v-if="showPublishedMeta" class="progress-generation-block">
            <p class="muted">{{ publishedGenerationCaption }}</p>
            <ul v-if="publishedGenerationLines.length" class="progress-meta-list">
              <li v-for="line in publishedGenerationLines" :key="line" class="progress-meta-item">{{ line }}</li>
            </ul>
          </div>

          <p v-if="loading" class="muted">开发进度加载中...</p>
          <template v-else>
            <div v-if="displayPublishedProgressDays.length" class="timeline progress-changelog">
              <article v-for="day in displayPublishedProgressDays" :key="day.id" class="timeline-item">
                <div class="timeline-date">{{ day.date }}</div>
                <div class="timeline-body">
                  <h4>{{ day.title }}</h4>
                  <div class="progress-repo-list">
                    <section v-for="repo in day.repos" :key="repo.id" class="progress-repo-card">
                      <div class="progress-repo-head">
                        <div>
                          <h5>{{ repo.repo_label }}</h5>
                        </div>
                        <span class="muted">{{ repo.updates.length }} 条更新</span>
                      </div>

                      <ul class="progress-update-list">
                        <li v-for="update in repo.updates" :key="update.id" class="progress-update-item">
                          <strong class="progress-update-title">{{ update.title }}</strong>
                          <p class="progress-update-description">{{ update.description }}</p>
                        </li>
                      </ul>
                    </section>
                  </div>
                </div>
              </article>
            </div>
            <p v-else class="muted">当前还没有已发布的开发日志。</p>
          </template>
        </section>
      </section>

      <section v-if="canManage" class="card progress-card progress-draft-card">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>草稿工作区</h3>
            <p class="muted">这里仅用于查看由 Codex 专用对话生成的草稿日志，确认无误后再发布。</p>
          </div>
          <div class="progress-hero-actions">
            <button class="btn secondary" :disabled="loading || publishing || !hasDraftContent" @click="handlePublish">
              {{ publishing ? '正在发布...' : '发布当前草稿' }}
            </button>
          </div>
        </div>

        <p class="muted">{{ draftMetaText }}</p>

        <div class="progress-generation-block">
          <p class="muted">{{ draftGenerationCaption }}</p>
          <ul v-if="draftGenerationLines.length" class="progress-meta-list">
            <li v-for="line in draftGenerationLines" :key="line" class="progress-meta-item">{{ line }}</li>
          </ul>
        </div>

        <div v-if="displayDraftProgressDays.length" class="timeline progress-changelog">
          <article v-for="day in displayDraftProgressDays" :key="day.id" class="timeline-item">
            <div class="timeline-date">{{ day.date }}</div>
            <div class="timeline-body">
              <h4>{{ day.title }}</h4>
              <div class="progress-repo-list">
                <section v-for="repo in day.repos" :key="repo.id" class="progress-repo-card">
                  <div class="progress-repo-head">
                    <div>
                      <h5>{{ repo.repo_label }}</h5>
                    </div>
                    <span class="muted">{{ repo.updates.length }} 条更新</span>
                  </div>

                  <ul class="progress-update-list">
                    <li v-for="update in repo.updates" :key="update.id" class="progress-update-item">
                      <strong class="progress-update-title">{{ update.title }}</strong>
                      <p class="progress-update-description">{{ update.description }}</p>
                    </li>
                  </ul>
                </section>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="progress-empty-state">
          <strong>当前没有草稿内容</strong>
          <span>请在这条 Codex 专用对话里生成中文开发日志；生成结果写入草稿后，这里会自动显示。</span>
        </div>
      </section>
    </main>
  </div>
</template>
