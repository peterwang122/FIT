import { defineStore } from 'pinia'

import {
  accountLogin as accountLoginApi,
  fetchMe as fetchMeApi,
  fetchSessions as fetchSessionsApi,
  guestLogin as guestLoginApi,
  logout as logoutApi,
  revokeSession as revokeSessionApi,
  searchUsers as searchUsersApi,
  sendSmsCode as sendSmsCodeApi,
  setPassword as setPasswordApi,
  smsLogin as smsLoginApi,
  updatePreferences as updatePreferencesApi,
  updateProfile as updateProfileApi,
} from '../api/auth'
import type {
  AuthSessionRecord,
  AuthUser,
  UpdatePreferencesPayload,
  UpdateProfilePayload,
} from '../types/auth'

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

function maskPhone(phone: string | null | undefined) {
  if (!phone) return ''
  return phone.replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2')
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as AuthUser | null,
    initialized: false,
    initializing: false,
    sessions: [] as AuthSessionRecord[],
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    isGuest: (state) => state.user?.role === 'guest',
    isRoot: (state) => state.user?.role === 'root',
    displayName: (state) => {
      if (!state.user) return ''
      const nickname = state.user.nickname?.trim()
      if (nickname) return nickname
      return state.user.username
    },
    secondaryIdentity: (state) => {
      if (!state.user) return ''
      if (state.user.phone) return maskPhone(state.user.phone)
      return state.user.username
    },
    avatarText(): string {
      const value = this.displayName.trim() || this.user?.username?.trim() || 'U'
      return value.slice(0, 1).toUpperCase()
    },
    roleLabel: (state) => {
      if (!state.user) return ''
      if (state.user.role === 'root') return 'ROOT'
      if (state.user.role === 'guest') return 'GUEST'
      return 'USER'
    },
  },
  actions: {
    async fetchMe() {
      if (this.initializing) return this.user
      this.initializing = true
      try {
        const data = await fetchMeApi()
        this.user = data.user
        return this.user
      } catch {
        this.user = null
        return null
      } finally {
        this.initialized = true
        this.initializing = false
      }
    },
    async ensureInitialized() {
      if (!this.initialized) {
        await this.fetchMe()
      }
    },
    async sendCode(phone: string) {
      try {
        return await sendSmsCodeApi({ phone })
      } catch (error) {
        throw new Error(extractErrorMessage(error, '验证码发送失败'))
      }
    },
    async smsLogin(phone: string, code: string) {
      try {
        const data = await smsLoginApi({ phone, code })
        this.user = data.user
        this.initialized = true
        this.sessions = []
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '验证码登录失败'))
      }
    },
    async accountLogin(account: string, password: string) {
      try {
        const data = await accountLoginApi({ account, password })
        this.user = data.user
        this.initialized = true
        this.sessions = []
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '账号密码登录失败'))
      }
    },
    async guestLogin() {
      try {
        const data = await guestLoginApi()
        this.user = data.user
        this.initialized = true
        this.sessions = []
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '游客登录失败'))
      }
    },
    async logout() {
      try {
        await logoutApi()
      } finally {
        this.user = null
        this.sessions = []
        this.initialized = true
      }
    },
    async setPassword(password: string, currentPassword?: string | null) {
      try {
        const data = await setPasswordApi({ password, current_password: currentPassword ?? null })
        this.user = data.user
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '密码设置失败'))
      }
    },
    async updateProfile(payload: UpdateProfilePayload) {
      try {
        const data = await updateProfileApi(payload)
        this.user = data.user
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '个人资料保存失败'))
      }
    },
    async updatePreferences(payload: UpdatePreferencesPayload) {
      try {
        const data = await updatePreferencesApi(payload)
        this.user = data.user
        return data.user
      } catch (error) {
        throw new Error(extractErrorMessage(error, '偏好设置保存失败'))
      }
    },
    async loadSessions() {
      try {
        const items = await fetchSessionsApi()
        this.sessions = items
        return items
      } catch (error) {
        throw new Error(extractErrorMessage(error, '会话列表加载失败'))
      }
    },
    async revokeSession(sessionId: number) {
      try {
        const item = await revokeSessionApi(sessionId)
        this.sessions = this.sessions.map((session) => (session.id === item.id ? item : session))
        if (item.is_current) {
          this.user = null
        }
        return item
      } catch (error) {
        throw new Error(extractErrorMessage(error, '会话下线失败'))
      }
    },
    async searchUsers(keyword: string) {
      try {
        return await searchUsersApi(keyword)
      } catch (error) {
        throw new Error(extractErrorMessage(error, '用户搜索失败'))
      }
    },
    setSessions(items: AuthSessionRecord[]) {
      this.sessions = items
    },
    setUser(user: AuthUser | null) {
      this.user = user
    },
    clearAuth() {
      this.user = null
      this.sessions = []
      this.initialized = true
    },
  },
})
