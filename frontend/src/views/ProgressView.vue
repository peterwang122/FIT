<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchProgressBoard, updateProgressBoard } from '../api/progress'
import AppSidebar from '../components/AppSidebar.vue'
import { useAuthStore } from '../stores/auth'
import type { ProgressBoardPayload, ProgressDay, ProgressEntry, ProgressTodoItem } from '../types/progress'

function makeId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function cloneData<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function compareDateText(left: string, right: string) {
  if (!left && !right) return 0
  if (!left) return 1
  if (!right) return -1
  return left.localeCompare(right)
}

function sortProgressDays(days: ProgressDay[]) {
  return [...days].sort((a, b) => compareDateText(a.date, b.date) || a.title.localeCompare(b.title))
}

function createTodo(text = ''): ProgressTodoItem {
  return {
    id: makeId(),
    text,
  }
}

function createProgressEntry(text = ''): ProgressEntry {
  return {
    id: makeId(),
    text,
  }
}

function createProgressDay(date = new Date().toISOString().slice(0, 10), title = '新的进度记录'): ProgressDay {
  return {
    id: makeId(),
    date,
    title,
    items: [createProgressEntry('')],
  }
}

function sanitizeTodoItems(items: ProgressTodoItem[]) {
  return items
    .map((item) => ({ ...item, text: item.text.trim() }))
    .filter((item) => item.text)
}

function sanitizeProgressDays(days: ProgressDay[]) {
  return sortProgressDays(
    days
      .map((day) => ({
        ...day,
        date: day.date.trim(),
        title: day.title.trim(),
        items: day.items.map((entry) => ({ ...entry, text: entry.text.trim() })).filter((entry) => entry.text),
      }))
      .filter((day) => day.date || day.title || day.items.length > 0),
  )
}

const authStore = useAuthStore()

const todoItems = ref<ProgressTodoItem[]>([])
const progressDays = ref<ProgressDay[]>([])
const draftTodoItems = ref<ProgressTodoItem[]>([])
const draftProgressDays = ref<ProgressDay[]>([])
const isEditing = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saveMessage = ref('')
const updatedAt = ref<string | null>(null)
const updatedByName = ref<string | null>(null)

const canEdit = computed(() => authStore.isRoot)
const displayTodoItems = computed(() => sanitizeTodoItems(todoItems.value))
const displayProgressDays = computed(() => sanitizeProgressDays(progressDays.value))
const saveHint = computed(() => {
  if (loading.value) return '正在加载共享开发进度...'
  if (isEditing.value) return '修改完成后点击“保存并返回”，所有用户都会看到更新后的共享进度。'
  if (!canEdit.value) return '当前是只读模式，只有 root 用户可以编辑共享开发进度。'
  if (updatedAt.value) {
    return `当前展示的是共享开发进度，最近更新：${updatedAt.value}${updatedByName.value ? ` / ${updatedByName.value}` : ''}`
  }
  return '当前展示的是共享开发进度。'
})

function applyBoard(payload: ProgressBoardPayload, meta?: { updated_at?: string | null; updated_by_name?: string | null }) {
  todoItems.value = payload.todo_items ?? []
  progressDays.value = sortProgressDays(payload.progress_days ?? [])
  updatedAt.value = meta?.updated_at ?? updatedAt.value
  updatedByName.value = meta?.updated_by_name ?? updatedByName.value
}

async function loadBoard() {
  loading.value = true
  error.value = ''
  try {
    const board = await fetchProgressBoard()
    applyBoard(
      {
        todo_items: board.todo_items,
        progress_days: board.progress_days,
      },
      { updated_at: board.updated_at, updated_by_name: board.updated_by_name },
    )
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '开发进度加载失败'
  } finally {
    loading.value = false
  }
}

function startEditing() {
  draftTodoItems.value = cloneData(todoItems.value)
  draftProgressDays.value = cloneData(progressDays.value)
  saveMessage.value = ''
  isEditing.value = true
}

function cancelEditing() {
  isEditing.value = false
  draftTodoItems.value = []
  draftProgressDays.value = []
}

async function saveAndExit() {
  saving.value = true
  error.value = ''
  saveMessage.value = ''
  try {
    const nextPayload: ProgressBoardPayload = {
      todo_items: sanitizeTodoItems(draftTodoItems.value),
      progress_days: sanitizeProgressDays(draftProgressDays.value),
    }
    const board = await updateProgressBoard(nextPayload)
    applyBoard(nextPayload, { updated_at: board.updated_at, updated_by_name: board.updated_by_name })
    saveMessage.value = '共享开发进度已更新'
    isEditing.value = false
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '开发进度保存失败'
  } finally {
    saving.value = false
  }
}

function addTodo() {
  draftTodoItems.value.unshift(createTodo(''))
}

function removeTodo(id: string) {
  draftTodoItems.value = draftTodoItems.value.filter((item) => item.id !== id)
}

function addProgressDay() {
  draftProgressDays.value = sortProgressDays([createProgressDay(), ...draftProgressDays.value])
}

function removeProgressDay(id: string) {
  draftProgressDays.value = draftProgressDays.value.filter((day) => day.id !== id)
}

function addProgressEntry(dayId: string) {
  const day = draftProgressDays.value.find((item) => item.id === dayId)
  if (!day) return
  day.items.push(createProgressEntry(''))
}

function removeProgressEntry(dayId: string, entryId: string) {
  const day = draftProgressDays.value.find((item) => item.id === dayId)
  if (!day) return
  day.items = day.items.filter((item) => item.id !== entryId)
  if (day.items.length === 0) {
    day.items.push(createProgressEntry(''))
  }
}

function sortDraftProgressDays() {
  draftProgressDays.value = sortProgressDays(draftProgressDays.value)
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
          <p class="progress-kicker">Development</p>
          <h2>开发进度</h2>
          <p class="muted">{{ saveHint }}</p>
        </div>

        <div class="progress-hero-actions">
          <template v-if="canEdit && isEditing">
            <button class="btn primary" :disabled="saving" @click="saveAndExit">
              {{ saving ? '保存中...' : '保存并返回' }}
            </button>
            <button class="btn" :disabled="saving" @click="cancelEditing">取消</button>
          </template>
          <button v-else-if="canEdit" class="btn primary" @click="startEditing">编辑内容</button>
          <span v-else class="account-readonly-tag">只读模式</span>
        </div>
      </section>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-else-if="saveMessage" class="banner-success">{{ saveMessage }}</p>

      <section class="progress-grid">
        <section class="card progress-card">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>TODO</h3>
              <p class="muted">{{ canEdit ? 'root 可以维护共享 TODO 列表。' : '当前展示的是共享 TODO 列表。' }}</p>
            </div>
            <button v-if="canEdit && isEditing" class="btn" @click="addTodo">新增 TODO</button>
          </div>

          <p v-if="loading" class="muted">开发进度加载中...</p>
          <template v-else-if="canEdit && isEditing">
            <div class="editable-list">
              <article v-for="item in draftTodoItems" :key="item.id" class="editable-card">
                <textarea
                  v-model="item.text"
                  class="input progress-textarea"
                  rows="4"
                  placeholder="输入待办内容"
                />
                <button class="btn progress-row-action" @click="removeTodo(item.id)">删除</button>
              </article>
            </div>
          </template>
          <template v-else>
            <ul v-if="displayTodoItems.length" class="progress-list">
              <li v-for="item in displayTodoItems" :key="item.id">{{ item.text }}</li>
            </ul>
            <p v-else class="muted">暂无待办项。</p>
          </template>
        </section>

        <section class="card progress-card progress-card-wide">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>每日进度</h3>
              <p class="muted">{{ canEdit ? '所有编辑都会实时保存为共享进度。' : '当前展示的是共享开发进度记录。' }}</p>
            </div>
            <button v-if="canEdit && isEditing" class="btn" @click="addProgressDay">新增日期</button>
          </div>

          <p v-if="loading" class="muted">开发进度加载中...</p>
          <template v-else-if="canEdit && isEditing">
            <div class="timeline">
              <article v-for="day in draftProgressDays" :key="day.id" class="timeline-item timeline-item-editable">
                <div class="timeline-date timeline-date-edit">
                  <label class="label-inline">日期</label>
                  <input v-model="day.date" type="date" class="input date-input" @change="sortDraftProgressDays" />
                  <button class="btn progress-row-action" @click="removeProgressDay(day.id)">删除记录</button>
                </div>

                <div class="timeline-body timeline-body-editable">
                  <input v-model="day.title" class="input progress-title-input" placeholder="输入当天进度标题" />

                  <div class="progress-day-items">
                    <div v-for="entry in day.items" :key="entry.id" class="editable-card editable-card-compact">
                      <textarea
                        v-model="entry.text"
                        class="input progress-textarea progress-textarea-compact"
                        rows="3"
                        placeholder="输入当天完成的事项"
                      />
                      <button class="btn progress-row-action" @click="removeProgressEntry(day.id, entry.id)">删除</button>
                    </div>
                  </div>

                  <div class="progress-day-actions">
                    <button class="btn" @click="addProgressEntry(day.id)">新增事项</button>
                  </div>
                </div>
              </article>
            </div>
          </template>
          <template v-else>
            <div v-if="displayProgressDays.length" class="timeline">
              <article v-for="day in displayProgressDays" :key="day.id" class="timeline-item">
                <div class="timeline-date">{{ day.date || '未填写日期' }}</div>
                <div class="timeline-body">
                  <h4>{{ day.title || '未填写标题' }}</h4>
                  <ul v-if="day.items.length" class="progress-list">
                    <li v-for="item in day.items" :key="item.id">{{ item.text }}</li>
                  </ul>
                  <p v-else class="muted">暂无事项。</p>
                </div>
              </article>
            </div>
            <p v-else class="muted">暂无每日进度记录。</p>
          </template>
        </section>
      </section>
    </main>
  </div>
</template>
