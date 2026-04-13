<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useAuthStore } from './stores/auth'
import { useNotificationStore } from './stores/notifications'
import type { UserNotification } from './types/notification'

const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const route = useRoute()
const router = useRouter()

const accountMenuOpen = ref(false)
const notificationMenuOpen = ref(false)
const accountMenuRef = ref<HTMLElement | null>(null)
const notificationMenuRef = ref<HTMLElement | null>(null)

const notifications = computed(() => notificationStore.items)

function closeAccountMenu() {
  accountMenuOpen.value = false
}

function closeNotificationMenu() {
  notificationMenuOpen.value = false
}

function closeMenus() {
  closeAccountMenu()
  closeNotificationMenu()
}

function toggleAccountMenu() {
  notificationMenuOpen.value = false
  accountMenuOpen.value = !accountMenuOpen.value
}

async function toggleNotificationMenu() {
  accountMenuOpen.value = false
  notificationMenuOpen.value = !notificationMenuOpen.value
  if (notificationMenuOpen.value && authStore.isAuthenticated) {
    await notificationStore.refreshQuietly()
  }
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target as Node | null
  if (!target) return
  if (accountMenuRef.value && !accountMenuRef.value.contains(target)) {
    closeAccountMenu()
  }
  if (notificationMenuRef.value && !notificationMenuRef.value.contains(target)) {
    closeNotificationMenu()
  }
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeMenus()
  }
}

function goToLogin(tab: 'sms' | 'account') {
  void router.push({
    path: '/login',
    query: tab === 'account' ? { tab: 'account' } : { tab: 'sms' },
  })
}

async function handleLogout() {
  closeMenus()
  await authStore.logout()
  notificationStore.clear()
  await router.push('/login?tab=account')
}

function goTo(path: string, tab?: string) {
  closeMenus()
  void router.push({
    path,
    query: tab ? { tab } : undefined,
  })
}

function formatNotificationTime(rawValue: string | null) {
  if (!rawValue) return '-'
  const value = new Date(rawValue)
  if (Number.isNaN(value.getTime())) return rawValue
  return value.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function openNotification(item: UserNotification) {
  if (!item.is_read) {
    await notificationStore.markRead(item.id)
  }
  closeMenus()
  if (item.action_url) {
    await router.push(item.action_url)
  }
}

async function handleMarkAllRead() {
  await notificationStore.markAllRead()
}

watch(
  () => route.fullPath,
  () => {
    closeMenus()
  },
)

watch(
  () => authStore.isAuthenticated,
  async (isAuthenticated) => {
    if (!isAuthenticated) {
      notificationStore.clear()
      return
    }
    await notificationStore.refreshQuietly()
    notificationStore.startPolling(60000)
  },
  { immediate: true },
)

onMounted(() => {
  void authStore.ensureInitialized()
  document.addEventListener('click', handleDocumentClick)
  document.addEventListener('keydown', handleEscape)
})

onBeforeUnmount(() => {
  notificationStore.stopPolling()
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleEscape)
})
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <div class="brand-lockup">
        <img src="/logo1-header.png" alt="FIT logo" class="brand-logo" />
        <div class="brand-copy">
          <h1>FIT 股票量化系统</h1>
          <p class="brand-subtitle">Fixed Immortal Travel Stock Quantitative Platform</p>
        </div>
      </div>

      <div class="site-header-actions">
        <template v-if="!authStore.isAuthenticated">
          <button type="button" class="btn btn-secondary btn-compact" @click="goToLogin('account')">登录</button>
          <button type="button" class="btn btn-primary btn-compact" @click="goToLogin('sms')">注册</button>
        </template>

        <template v-else>
          <div ref="notificationMenuRef" class="notification-menu-wrap">
            <button
              type="button"
              class="notification-trigger"
              :class="{ active: notificationMenuOpen }"
              @click="toggleNotificationMenu"
            >
              <span class="notification-icon">🔔</span>
              <span v-if="notificationStore.unreadCount" class="notification-badge">
                {{ notificationStore.unreadCount > 99 ? '99+' : notificationStore.unreadCount }}
              </span>
            </button>

            <div v-if="notificationMenuOpen" class="notification-dropdown card">
              <div class="notification-dropdown-head">
                <div>
                  <strong>站内消息</strong>
                  <span>最近消息与待处理提醒</span>
                </div>
                <button
                  type="button"
                  class="btn btn-secondary btn-compact"
                  :disabled="!notificationStore.unreadCount"
                  @click="handleMarkAllRead"
                >
                  全部已读
                </button>
              </div>

              <div v-if="notifications.length" class="notification-list">
                <button
                  v-for="item in notifications"
                  :key="item.id"
                  type="button"
                  class="notification-item"
                  :class="{ unread: !item.is_read }"
                  @click="openNotification(item)"
                >
                  <div class="notification-item-head">
                    <strong>{{ item.title }}</strong>
                    <span>{{ formatNotificationTime(item.created_at) }}</span>
                  </div>
                  <p>{{ item.body }}</p>
                  <span v-if="item.action_label" class="notification-action">{{ item.action_label }}</span>
                </button>
              </div>
              <div v-else class="notification-empty">
                <strong>暂无消息</strong>
                <span>新的策略派发与采集提醒会显示在这里。</span>
              </div>
            </div>
          </div>

          <div ref="accountMenuRef" class="account-menu-wrap">
            <button type="button" class="account-menu-trigger" @click="toggleAccountMenu">
              <div class="account-avatar">{{ authStore.avatarText }}</div>
              <div class="account-copy">
                <strong>{{ authStore.displayName }}</strong>
                <span>{{ authStore.secondaryIdentity }}</span>
              </div>
              <span class="account-role">{{ authStore.roleLabel }}</span>
            </button>

            <div v-if="accountMenuOpen" class="account-dropdown card">
              <button type="button" class="account-dropdown-item" @click="goTo('/account', 'profile')">
                <strong>个人中心</strong>
                <span>管理昵称、邮箱、公司与简介</span>
              </button>
              <button type="button" class="account-dropdown-item" @click="goTo('/account', 'security')">
                <strong>账号安全</strong>
                <span>修改密码、设备管理、最近登录</span>
              </button>
              <button type="button" class="account-dropdown-item" @click="goTo('/quant/strategies')">
                <strong>我的策略</strong>
                <span>查看和管理当前账户的策略</span>
              </button>
              <button type="button" class="account-dropdown-item" @click="goTo('/progress')">
                <strong>开发进度</strong>
                <span>查看共享开发进度{{ authStore.isRoot ? '，root 可编辑' : '（只读）' }}</span>
              </button>
              <button type="button" class="account-dropdown-item account-dropdown-item-danger" @click="handleLogout">
                <strong>退出登录</strong>
                <span>结束当前登录会话</span>
              </button>
            </div>
          </div>
        </template>
      </div>
    </header>

    <RouterView />
  </div>
</template>
