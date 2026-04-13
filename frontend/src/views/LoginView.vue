<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const loginMode = ref<'sms' | 'account'>('sms')
const phone = ref('')
const code = ref('')
const account = ref('')
const password = ref('')
const codeSending = ref(false)
const submitting = ref(false)
const message = ref('')
const error = ref('')

const redirectPath = computed(() => {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.trim()) {
    return redirect
  }
  return authStore.user?.preferences?.default_homepage || '/'
})

function syncLoginMode() {
  loginMode.value = route.query.tab === 'account' ? 'account' : 'sms'
}

async function finishLogin() {
  await router.push(redirectPath.value)
}

async function handleSendCode() {
  error.value = ''
  message.value = ''
  codeSending.value = true
  try {
    await authStore.sendCode(phone.value)
    message.value = '验证码已发送，请留意短信或后端调试日志。'
  } catch (sendError) {
    error.value = sendError instanceof Error ? sendError.message : '验证码发送失败'
  } finally {
    codeSending.value = false
  }
}

async function handleSmsLogin() {
  error.value = ''
  message.value = ''
  submitting.value = true
  try {
    await authStore.smsLogin(phone.value, code.value)
    await finishLogin()
  } catch (loginError) {
    error.value = loginError instanceof Error ? loginError.message : '验证码登录失败'
  } finally {
    submitting.value = false
  }
}

async function handleAccountLogin() {
  error.value = ''
  message.value = ''
  submitting.value = true
  try {
    await authStore.accountLogin(account.value, password.value)
    await finishLogin()
  } catch (loginError) {
    error.value = loginError instanceof Error ? loginError.message : '账号密码登录失败'
  } finally {
    submitting.value = false
  }
}

async function handleGuestLogin() {
  error.value = ''
  message.value = ''
  submitting.value = true
  try {
    await authStore.guestLogin()
    await finishLogin()
  } catch (loginError) {
    error.value = loginError instanceof Error ? loginError.message : '游客登录失败'
  } finally {
    submitting.value = false
  }
}

watch(
  () => route.query.tab,
  () => {
    syncLoginMode()
  },
  { immediate: true },
)

watch(
  () => authStore.isAuthenticated,
  async (isAuthenticated) => {
    if (isAuthenticated) {
      await finishLogin()
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="login-shell">
    <section class="card login-card">
      <div class="login-card-copy">
        <span class="eyebrow">用户登录</span>
        <h2>进入 FIT 股票量化系统</h2>
        <p class="muted">
          普通用户可用手机号验证码直接注册并登录，也可以在设置密码后使用手机号 + 密码登录；root 与 guest 支持账号密码登录。
        </p>
      </div>

      <div class="login-mode-switch">
        <button
          type="button"
          class="segmented-pill"
          :class="{ active: loginMode === 'sms' }"
          @click="router.replace({ path: '/login', query: route.query.redirect ? { ...route.query, tab: 'sms' } : { tab: 'sms' } })"
        >
          手机验证码
        </button>
        <button
          type="button"
          class="segmented-pill"
          :class="{ active: loginMode === 'account' }"
          @click="router.replace({ path: '/login', query: route.query.redirect ? { ...route.query, tab: 'account' } : { tab: 'account' } })"
        >
          账号密码
        </button>
      </div>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-else-if="message" class="banner-success">{{ message }}</p>

      <form v-if="loginMode === 'sms'" class="login-form" @submit.prevent="handleSmsLogin">
        <label class="quant-field">
          <span class="quant-field-label">手机号</span>
          <input v-model.trim="phone" class="input" inputmode="numeric" placeholder="请输入 11 位手机号" />
        </label>
        <div class="login-code-row">
          <label class="quant-field">
            <span class="quant-field-label">验证码</span>
            <input v-model.trim="code" class="input" inputmode="numeric" placeholder="请输入验证码" />
          </label>
          <button type="button" class="btn btn-secondary" :disabled="codeSending || !phone" @click="handleSendCode">
            {{ codeSending ? '发送中...' : '发送验证码' }}
          </button>
        </div>
        <button type="submit" class="btn btn-primary" :disabled="submitting || !phone || !code">
          {{ submitting ? '登录中...' : '验证码登录 / 注册' }}
        </button>
      </form>

      <form v-else class="login-form" @submit.prevent="handleAccountLogin">
        <label class="quant-field">
          <span class="quant-field-label">账号</span>
          <input
            v-model.trim="account"
            class="input"
            placeholder="普通用户填手机号，root / guest 填账号名"
          />
        </label>
        <label class="quant-field">
          <span class="quant-field-label">密码</span>
          <input v-model="password" class="input" type="password" placeholder="请输入密码" />
        </label>
        <button type="submit" class="btn btn-primary" :disabled="submitting || !account || !password">
          {{ submitting ? '登录中...' : '账号密码登录' }}
        </button>
      </form>

      <div class="login-guest">
        <span class="login-guest-copy">临时体验可直接进入共享游客空间。</span>
        <button type="button" class="btn btn-secondary" :disabled="submitting" @click="handleGuestLogin">
          {{ submitting ? '处理中...' : '游客一键进入' }}
        </button>
      </div>
    </section>
  </div>
</template>
