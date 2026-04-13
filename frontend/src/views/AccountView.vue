<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppSidebar from '../components/AppSidebar.vue'
import { useAuthStore } from '../stores/auth'
import type { UpdatePreferencesPayload, UpdateProfilePayload } from '../types/auth'

type AccountTab = 'profile' | 'security' | 'preferences' | 'privacy'

const TAB_OPTIONS: Array<{ key: AccountTab; label: string; description: string }> = [
  { key: 'profile', label: '个人资料', description: '管理昵称、邮箱、公司与简介。' },
  { key: 'security', label: '账号安全', description: '管理密码、当前设备与最近登录记录。' },
  { key: 'preferences', label: '偏好设置', description: '设置主题、语言、通知与默认首页。' },
  { key: 'privacy', label: '隐私与数据', description: '查看权限说明与后续开放能力。' },
]

const DEFAULT_PREFERENCES: UpdatePreferencesPayload = {
  theme: 'system',
  language: 'zh-CN',
  notifications_enabled: true,
  default_homepage: '/',
}

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const activeTab = ref<AccountTab>('profile')
const profileDraft = reactive<UpdateProfilePayload>({
  nickname: '',
  email: null,
  company: '',
  bio: '',
})
const preferencesDraft = reactive<UpdatePreferencesPayload>({ ...DEFAULT_PREFERENCES })
const profileSaving = ref(false)
const preferencesSaving = ref(false)
const sessionsLoading = ref(false)
const passwordSaving = ref(false)
const passwordDraft = reactive({
  currentPassword: '',
  nextPassword: '',
  confirmPassword: '',
})
const profileMessage = ref('')
const preferencesMessage = ref('')
const passwordMessage = ref('')
const error = ref('')

const canManagePassword = computed(() => authStore.isAuthenticated && !authStore.isGuest)
const accountDisplayName = computed(() => authStore.displayName || authStore.user?.username || '用户')
const accountSecondaryLine = computed(() => authStore.secondaryIdentity || authStore.user?.username || '')

function syncDrafts() {
  const user = authStore.user
  if (!user) return
  profileDraft.nickname = user.nickname ?? ''
  profileDraft.email = user.email ?? null
  profileDraft.company = user.company ?? ''
  profileDraft.bio = user.bio ?? ''
  preferencesDraft.theme = user.preferences?.theme ?? DEFAULT_PREFERENCES.theme
  preferencesDraft.language = user.preferences?.language ?? DEFAULT_PREFERENCES.language
  preferencesDraft.notifications_enabled = user.preferences?.notifications_enabled ?? DEFAULT_PREFERENCES.notifications_enabled
  preferencesDraft.default_homepage = user.preferences?.default_homepage ?? DEFAULT_PREFERENCES.default_homepage
}

function resolveTab(value: unknown): AccountTab {
  return TAB_OPTIONS.some((item) => item.key === value) ? (value as AccountTab) : 'profile'
}

async function ensureSessionsLoaded() {
  if (!authStore.isAuthenticated) return
  sessionsLoading.value = true
  try {
    await authStore.loadSessions()
  } catch (sessionError) {
    error.value = sessionError instanceof Error ? sessionError.message : '会话列表加载失败'
  } finally {
    sessionsLoading.value = false
  }
}

async function handleSaveProfile() {
  error.value = ''
  profileMessage.value = ''
  profileSaving.value = true
  try {
    await authStore.updateProfile({
      nickname: profileDraft.nickname.trim(),
      email: profileDraft.email?.trim() || null,
      company: profileDraft.company.trim(),
      bio: profileDraft.bio.trim(),
    })
    profileMessage.value = '个人资料已保存'
    syncDrafts()
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '个人资料保存失败'
  } finally {
    profileSaving.value = false
  }
}

async function handleSavePreferences() {
  error.value = ''
  preferencesMessage.value = ''
  preferencesSaving.value = true
  try {
    await authStore.updatePreferences({
      theme: preferencesDraft.theme,
      language: preferencesDraft.language,
      notifications_enabled: preferencesDraft.notifications_enabled,
      default_homepage: preferencesDraft.default_homepage,
    })
    preferencesMessage.value = '偏好设置已保存'
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '偏好设置保存失败'
  } finally {
    preferencesSaving.value = false
  }
}

async function handleSetPassword() {
  error.value = ''
  passwordMessage.value = ''
  if (!passwordDraft.nextPassword || passwordDraft.nextPassword.length < 6) {
    error.value = '新密码长度至少为 6 位'
    return
  }
  if (passwordDraft.nextPassword !== passwordDraft.confirmPassword) {
    error.value = '两次输入的新密码不一致'
    return
  }
  passwordSaving.value = true
  try {
    await authStore.setPassword(passwordDraft.nextPassword, passwordDraft.currentPassword || null)
    passwordDraft.currentPassword = ''
    passwordDraft.nextPassword = ''
    passwordDraft.confirmPassword = ''
    passwordMessage.value = '密码已更新'
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '密码设置失败'
  } finally {
    passwordSaving.value = false
  }
}

async function handleRevokeSession(sessionId: number, isCurrent: boolean) {
  if (isCurrent) return
  if (!window.confirm('确定下线这个会话吗？')) return
  error.value = ''
  try {
    await authStore.revokeSession(sessionId)
    await ensureSessionsLoaded()
  } catch (sessionError) {
    error.value = sessionError instanceof Error ? sessionError.message : '会话下线失败'
  }
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function switchTab(tab: AccountTab) {
  activeTab.value = tab
  void router.replace({
    path: '/account',
    query: tab === 'profile' ? undefined : { tab },
  })
}

watch(
  () => route.query.tab,
  (value) => {
    activeTab.value = resolveTab(value)
  },
  { immediate: true },
)

watch(
  () => authStore.user,
  () => {
    syncDrafts()
  },
  { immediate: true },
)

onMounted(async () => {
  await authStore.ensureInitialized()
  syncDrafts()
  await ensureSessionsLoaded()
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="account" />

    <main class="dashboard-main account-main">
      <section class="card account-hero">
        <div class="account-hero-identify">
          <div class="account-avatar account-avatar-large">{{ authStore.avatarText }}</div>
          <div class="account-hero-copy">
            <p class="progress-kicker">Account Center</p>
            <h2>{{ accountDisplayName }}</h2>
            <p class="muted">{{ accountSecondaryLine }}</p>
            <div class="account-role-badge">{{ authStore.roleLabel }}</div>
          </div>
        </div>
        <div class="account-hero-summary">
          <div>
            <div class="label">账号名</div>
            <div class="value small">{{ authStore.user?.username ?? '-' }}</div>
          </div>
          <div>
            <div class="label">手机号</div>
            <div class="value small">{{ authStore.user?.phone ?? '-' }}</div>
          </div>
          <div>
            <div class="label">注册时间</div>
            <div class="value small">{{ formatTime(authStore.user?.created_at ?? null) }}</div>
          </div>
          <div>
            <div class="label">最近登录</div>
            <div class="value small">{{ formatTime(authStore.user?.last_login_at ?? null) }}</div>
          </div>
        </div>
      </section>

      <p v-if="error" class="banner-error">{{ error }}</p>

      <section class="account-layout">
        <aside class="card account-nav">
          <button
            v-for="item in TAB_OPTIONS"
            :key="item.key"
            type="button"
            class="account-nav-item"
            :class="{ active: activeTab === item.key }"
            @click="switchTab(item.key)"
          >
            <strong>{{ item.label }}</strong>
            <span>{{ item.description }}</span>
          </button>
        </aside>

        <section class="card account-panel">
          <template v-if="activeTab === 'profile'">
            <div class="account-panel-head">
              <div>
                <h3>个人资料</h3>
                <p class="muted">头像暂时使用默认字母头像，当前版本不支持上传。</p>
              </div>
            </div>

            <p v-if="profileMessage" class="banner-success">{{ profileMessage }}</p>

            <div class="quant-strategy-form account-form-grid">
              <label class="quant-field">
                <span class="quant-field-label">昵称</span>
                <input v-model="profileDraft.nickname" class="input" placeholder="给自己起一个展示昵称" />
              </label>
              <label class="quant-field">
                <span class="quant-field-label">邮箱</span>
                <input v-model="profileDraft.email" class="input" type="email" placeholder="name@example.com" />
              </label>
              <label class="quant-field">
                <span class="quant-field-label">公司</span>
                <input v-model="profileDraft.company" class="input" placeholder="可选" />
              </label>
              <label class="quant-field">
                <span class="quant-field-label">角色</span>
                <input :value="authStore.user?.role ?? '-'" class="input" readonly />
              </label>
              <label class="quant-field quant-field-full">
                <span class="quant-field-label">简介</span>
                <textarea
                  v-model="profileDraft.bio"
                  class="input progress-textarea progress-textarea-compact"
                  placeholder="介绍一下你的使用偏好、研究方向或团队信息"
                />
              </label>
            </div>

            <div class="progress-hero-actions">
              <button class="btn btn-primary" :disabled="profileSaving" @click="handleSaveProfile">
                {{ profileSaving ? '保存中...' : '保存个人资料' }}
              </button>
            </div>
          </template>

          <template v-else-if="activeTab === 'security'">
            <div class="account-panel-head">
              <div>
                <h3>账号安全</h3>
                <p class="muted">管理密码、多设备登录以及最近登录记录。</p>
              </div>
            </div>

            <p v-if="passwordMessage" class="banner-success">{{ passwordMessage }}</p>

            <section class="account-section">
              <div class="account-section-head">
                <h4>修改密码</h4>
                <span class="muted">{{ canManagePassword ? '支持账号密码登录' : '游客账号不支持修改密码' }}</span>
              </div>
              <div class="quant-strategy-form account-form-grid">
                <label class="quant-field">
                  <span class="quant-field-label">当前密码</span>
                  <input
                    v-model="passwordDraft.currentPassword"
                    class="input"
                    type="password"
                    :disabled="!canManagePassword"
                    placeholder="如已有密码请先输入"
                  />
                </label>
                <label class="quant-field">
                  <span class="quant-field-label">新密码</span>
                  <input
                    v-model="passwordDraft.nextPassword"
                    class="input"
                    type="password"
                    :disabled="!canManagePassword"
                    placeholder="至少 6 位"
                  />
                </label>
                <label class="quant-field">
                  <span class="quant-field-label">确认新密码</span>
                  <input
                    v-model="passwordDraft.confirmPassword"
                    class="input"
                    type="password"
                    :disabled="!canManagePassword"
                    placeholder="再次输入新密码"
                  />
                </label>
              </div>
              <button class="btn btn-primary" :disabled="passwordSaving || !canManagePassword" @click="handleSetPassword">
                {{ passwordSaving ? '保存中...' : '更新密码' }}
              </button>
            </section>

            <section class="account-section">
              <div class="account-section-head">
                <h4>当前设备与多设备登录</h4>
                <span class="muted">可下线其他设备，当前设备不会在这里被误踢下线。</span>
              </div>
              <p v-if="sessionsLoading" class="muted">会话信息加载中...</p>
              <div v-else class="account-session-list">
                <article v-for="session in authStore.sessions" :key="session.id" class="account-session-card">
                  <div class="account-session-copy">
                    <strong>{{ session.is_current ? '当前设备' : '其他设备' }}</strong>
                    <span>{{ session.user_agent || '未知设备' }}</span>
                    <span>IP：{{ session.ip_address || '-' }}</span>
                    <span>登录：{{ formatTime(session.created_at) }}</span>
                    <span>最近活跃：{{ formatTime(session.last_seen_at) }}</span>
                    <span>过期：{{ formatTime(session.expires_at) }}</span>
                  </div>
                  <button
                    v-if="!session.is_current"
                    class="btn btn-secondary"
                    @click="handleRevokeSession(session.id, session.is_current)"
                  >
                    下线
                  </button>
                </article>
                <p v-if="!authStore.sessions.length" class="muted">暂无登录记录。</p>
              </div>
            </section>

            <section class="account-section">
              <div class="account-section-head">
                <h4>后续支持</h4>
              </div>
              <ul class="progress-list">
                <li>绑定手机：当前版本暂不开放换绑，普通用户账号仍以手机号为唯一标识。</li>
                <li>邮箱验证：后续开放，用于增强账号找回与安全通知。</li>
                <li>MFA：后续开放，当前仅保留入口说明。</li>
              </ul>
            </section>
          </template>

          <template v-else-if="activeTab === 'preferences'">
            <div class="account-panel-head">
              <div>
                <h3>偏好设置</h3>
                <p class="muted">偏好会跟随账号保存，并在下次登录后继续生效。</p>
              </div>
            </div>

            <p v-if="preferencesMessage" class="banner-success">{{ preferencesMessage }}</p>

            <div class="quant-strategy-form account-form-grid">
              <label class="quant-field">
                <span class="quant-field-label">主题</span>
                <select v-model="preferencesDraft.theme" class="input">
                  <option value="system">跟随系统</option>
                  <option value="light">浅色</option>
                  <option value="dark">深色</option>
                </select>
              </label>
              <label class="quant-field">
                <span class="quant-field-label">语言</span>
                <select v-model="preferencesDraft.language" class="input">
                  <option value="zh-CN">简体中文</option>
                  <option value="en-US">English</option>
                </select>
              </label>
              <label class="quant-field">
                <span class="quant-field-label">默认首页</span>
                <select v-model="preferencesDraft.default_homepage" class="input">
                  <option value="/">首页总览</option>
                  <option value="/stocks">个股行情</option>
                  <option value="/quant/index">量化分析 - 指数</option>
                  <option value="/quant/stock">量化分析 - 股票</option>
                  <option value="/quant/strategies">策略回测</option>
                  <option value="/progress">开发进度</option>
                </select>
              </label>
              <label class="account-switch">
                <input v-model="preferencesDraft.notifications_enabled" type="checkbox" />
                <div>
                  <strong>通知开关</strong>
                  <span>当前只保存偏好，后续会接入真实通知模块。</span>
                </div>
              </label>
            </div>

            <div class="progress-hero-actions">
              <button class="btn btn-primary" :disabled="preferencesSaving" @click="handleSavePreferences">
                {{ preferencesSaving ? '保存中...' : '保存偏好设置' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="account-panel-head">
              <div>
                <h3>隐私与数据</h3>
                <p class="muted">本页先集中说明权限和后续开放能力，不混入业务数据。</p>
              </div>
            </div>

            <section class="account-section">
              <div class="account-section-head">
                <h4>当前权限说明</h4>
              </div>
              <ul class="progress-list">
                <li>行情、图表和采集能力仍是共享系统能力，不按用户切分。</li>
                <li>量化分析相关策略按当前登录用户独立隔离。</li>
                <li>游客账号策略空间与正式用户、root 策略完全隔离。</li>
              </ul>
            </section>

            <section class="account-section">
              <div class="account-section-head">
                <h4>后续开放</h4>
              </div>
              <ul class="progress-list">
                <li>数据导出：后续会支持导出个人资料和策略配置。</li>
                <li>账号注销：后续会开放自助申请与确认流程。</li>
                <li>邮箱验证与更强隐私控制：后续逐步补齐。</li>
              </ul>
            </section>
          </template>
        </section>
      </section>
    </main>
  </div>
</template>
