export type AuthRole = 'root' | 'guest' | 'user'

export interface AuthPreferences {
  theme: string
  language: string
  notifications_enabled: boolean
  default_homepage: string
}

export interface AuthUser {
  id: number
  username: string
  phone: string | null
  role: AuthRole
  has_password: boolean
  nickname: string
  email: string | null
  company: string
  bio: string
  created_at: string | null
  last_login_at: string | null
  preferences: AuthPreferences
}

export interface AuthMeResponse {
  user: AuthUser
}

export interface SendSmsCodePayload {
  phone: string
}

export interface SmsLoginPayload {
  phone: string
  code: string
}

export interface AccountLoginPayload {
  account: string
  password: string
}

export interface SetPasswordPayload {
  password: string
  current_password?: string | null
}

export interface UpdateProfilePayload {
  nickname: string
  email: string | null
  company: string
  bio: string
}

export interface UpdatePreferencesPayload {
  theme: string
  language: string
  notifications_enabled: boolean
  default_homepage: string
}

export interface AuthSessionRecord {
  id: number
  user_agent: string
  ip_address: string
  created_at: string | null
  last_seen_at: string | null
  expires_at: string | null
  revoked_at: string | null
  is_current: boolean
  is_active: boolean
}

export interface UserSearchResult {
  id: number
  username: string
  phone: string | null
  nickname: string
  role: AuthRole
}
