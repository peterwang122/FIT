<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import AppSidebar from '../components/AppSidebar.vue'

type TodoItem = {
  id: string
  text: string
}

type ProgressEntry = {
  id: string
  text: string
}

type ProgressDay = {
  id: string
  date: string
  title: string
  items: ProgressEntry[]
}

const STORAGE_KEY = 'fit-progress-board-v1'

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

function createTodo(text = ''): TodoItem {
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

function defaultTodoItems(): TodoItem[] {
  return [
    createTodo('补充自动化测试与前端构建校验，形成稳定发布流程。'),
    createTodo('继续优化首页细节交互，包括图表密度、导航体验与移动端适配。'),
    createTodo('补齐更多市场数据模块的异常提示与空数据处理。'),
  ]
}

function defaultProgressDays(): ProgressDay[] {
  return sortProgressDays([
    {
      id: makeId(),
      date: '2026-03-12',
      title: '基础展示框架搭建',
      items: [
        createProgressEntry('完成前端 UI 重构，接入 Flower 任务监控入口。'),
        createProgressEntry('支持读取现有数据库字段映射，兼容已有表结构。'),
        createProgressEntry('增加数据库连接检查能力，便于确认系统可用性。'),
      ],
    },
    {
      id: makeId(),
      date: '2026-03-13',
      title: '股票 K 线与查询链路完善',
      items: [
        createProgressEntry('补上默认股票 002594 的展示与搜索流程。'),
        createProgressEntry('修复 lightweight-charts 兼容问题、超时与网络错误。'),
        createProgressEntry('优化代理与 CORS 配置，降低 K 线请求失败率。'),
      ],
    },
    {
      id: makeId(),
      date: '2026-03-14',
      title: '搜索与图表能力增强',
      items: [
        createProgressEntry('加入 Redis 驱动的股票搜索缓存。'),
        createProgressEntry('补齐 K 线完整字段与悬浮明细信息。'),
        createProgressEntry('处理可空数值字段，避免接口校验报错。'),
      ],
    },
    {
      id: makeId(),
      date: '2026-03-15',
      title: '多市场首页扩展',
      items: [
        createProgressEntry('首页扩展出指数 K 线、汇率 K 线、指数情绪指标和中金所净持仓表。'),
        createProgressEntry('增加日期选择、首页布局重排以及 logo 与品牌头部更新。'),
        createProgressEntry('继续微调首屏比例、表格布局和视觉细节。'),
      ],
    },
  ])
}

function normalizeTodoItems(raw: unknown): TodoItem[] {
  if (!Array.isArray(raw)) {
    return defaultTodoItems()
  }

  const result = raw
    .map((item) => {
      if (typeof item === 'string') {
        return createTodo(item)
      }
      if (!item || typeof item !== 'object') {
        return null
      }
      const candidate = item as Partial<TodoItem>
      return {
        id: typeof candidate.id === 'string' && candidate.id ? candidate.id : makeId(),
        text: typeof candidate.text === 'string' ? candidate.text : '',
      }
    })
    .filter((item): item is TodoItem => Boolean(item))

  return result.length > 0 ? result : defaultTodoItems()
}

function normalizeProgressEntries(raw: unknown): ProgressEntry[] {
  if (!Array.isArray(raw)) {
    return [createProgressEntry('')]
  }

  const result = raw
    .map((item) => {
      if (typeof item === 'string') {
        return createProgressEntry(item)
      }
      if (!item || typeof item !== 'object') {
        return null
      }
      const candidate = item as Partial<ProgressEntry>
      return {
        id: typeof candidate.id === 'string' && candidate.id ? candidate.id : makeId(),
        text: typeof candidate.text === 'string' ? candidate.text : '',
      }
    })
    .filter((item): item is ProgressEntry => Boolean(item))

  return result.length > 0 ? result : [createProgressEntry('')]
}

function normalizeProgressDays(raw: unknown): ProgressDay[] {
  if (!Array.isArray(raw)) {
    return defaultProgressDays()
  }

  const result = raw
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return null
      }
      const candidate = item as Partial<ProgressDay>
      return {
        id: typeof candidate.id === 'string' && candidate.id ? candidate.id : makeId(),
        date: typeof candidate.date === 'string' ? candidate.date : '',
        title: typeof candidate.title === 'string' ? candidate.title : '',
        items: normalizeProgressEntries(candidate.items),
      }
    })
    .filter((item): item is ProgressDay => Boolean(item))

  return result.length > 0 ? sortProgressDays(result) : defaultProgressDays()
}

function sanitizeTodoItems(items: TodoItem[]) {
  return items
    .map((item) => ({
      ...item,
      text: item.text.trim(),
    }))
    .filter((item) => item.text)
}

function sanitizeProgressDays(days: ProgressDay[]) {
  return sortProgressDays(
    days
      .map((day) => ({
        ...day,
        date: day.date.trim(),
        title: day.title.trim(),
        items: day.items
          .map((entry) => ({
            ...entry,
            text: entry.text.trim(),
          }))
          .filter((entry) => entry.text),
      }))
      .filter((day) => day.date || day.title || day.items.length > 0),
  )
}

const todoItems = ref<TodoItem[]>(defaultTodoItems())
const progressDays = ref<ProgressDay[]>(defaultProgressDays())
const draftTodoItems = ref<TodoItem[]>([])
const draftProgressDays = ref<ProgressDay[]>([])
const isEditing = ref(false)
const hasLocalDraft = ref(false)
const lastSavedAt = ref('')

const displayTodoItems = computed(() => sanitizeTodoItems(todoItems.value))
const displayProgressDays = computed(() => sanitizeProgressDays(progressDays.value))
const saveHint = computed(() => {
  if (isEditing.value) {
    return '修改完成后点击“保存并返回”，页面会回到展示状态。'
  }
  if (lastSavedAt.value) {
    return `当前展示的是已保存内容，最近保存时间：${lastSavedAt.value}`
  }
  if (hasLocalDraft.value) {
    return '当前展示的是已保存内容。'
  }
  return '点击编辑按钮后即可维护 TODO 和每日进度。'
})

function persistBoard(nextTodoItems: TodoItem[], nextProgressDays: ProgressDay[]) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      todoItems: nextTodoItems,
      progressDays: nextProgressDays,
    }),
  )
}

function loadBoard() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (!saved) {
      return
    }
    const parsed = JSON.parse(saved)
    todoItems.value = normalizeTodoItems(parsed?.todoItems ?? parsed?.todos)
    progressDays.value = normalizeProgressDays(parsed?.progressDays ?? parsed?.days)
    hasLocalDraft.value = true
  } catch (error) {
    console.error('读取开发进度失败', error)
  }
}

function startEditing() {
  draftTodoItems.value = cloneData(todoItems.value)
  draftProgressDays.value = cloneData(progressDays.value)
  isEditing.value = true
}

function cancelEditing() {
  isEditing.value = false
}

function saveAndExit() {
  const nextTodoItems = sanitizeTodoItems(draftTodoItems.value)
  const nextProgressDays = sanitizeProgressDays(draftProgressDays.value)
  todoItems.value = nextTodoItems
  progressDays.value = nextProgressDays

  try {
    persistBoard(nextTodoItems, nextProgressDays)
    lastSavedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    hasLocalDraft.value = true
  } catch (error) {
    console.error('保存开发进度失败', error)
  }

  isEditing.value = false
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
  if (!day) {
    return
  }
  day.items.push(createProgressEntry(''))
}

function removeProgressEntry(dayId: string, entryId: string) {
  const day = draftProgressDays.value.find((item) => item.id === dayId)
  if (!day) {
    return
  }
  day.items = day.items.filter((item) => item.id !== entryId)
  if (day.items.length === 0) {
    day.items.push(createProgressEntry(''))
  }
}

function sortDraftProgressDays() {
  draftProgressDays.value = sortProgressDays(draftProgressDays.value)
}

function resetDraftBoard() {
  if (!window.confirm('确定恢复默认内容吗？当前正在编辑的内容会被覆盖。')) {
    return
  }
  draftTodoItems.value = defaultTodoItems()
  draftProgressDays.value = defaultProgressDays()
}

onMounted(() => {
  loadBoard()
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
          <template v-if="isEditing">
            <button class="btn primary" @click="saveAndExit">保存并返回</button>
            <button class="btn" @click="cancelEditing">取消</button>
            <button class="btn" @click="resetDraftBoard">恢复默认</button>
          </template>
          <button v-else class="btn primary" @click="startEditing">编辑内容</button>
        </div>
      </section>

      <section class="progress-grid">
        <section class="card progress-card">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>TODO</h3>
              <p class="muted">
                {{ isEditing ? '编辑完成后点击保存并返回。' : '当前展示的是已保存的待办内容。' }}
              </p>
            </div>
            <button v-if="isEditing" class="btn" @click="addTodo">新增 TODO</button>
          </div>

          <template v-if="isEditing">
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
              <p class="muted">
                {{ isEditing ? '日期会按顺序自动整理。' : '当前展示的是已保存的每日进度记录。' }}
              </p>
            </div>
            <button v-if="isEditing" class="btn" @click="addProgressDay">新增日期</button>
          </div>

          <template v-if="isEditing">
            <div class="timeline">
              <article v-for="day in draftProgressDays" :key="day.id" class="timeline-item timeline-item-editable">
                <div class="timeline-date timeline-date-edit">
                  <label class="label-inline">日期</label>
                  <input
                    v-model="day.date"
                    type="date"
                    class="input date-input"
                    @change="sortDraftProgressDays"
                  />
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
                      <button class="btn progress-row-action" @click="removeProgressEntry(day.id, entry.id)">
                        删除
                      </button>
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
