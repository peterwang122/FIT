import { http } from './client'
import type {
  AccountLoginPayload,
  AuthMeResponse,
  AuthSessionRecord,
  SendSmsCodePayload,
  SetPasswordPayload,
  SmsLoginPayload,
  UpdatePreferencesPayload,
  UpdateProfilePayload,
  UserSearchResult,
} from '../types/auth'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function sendSmsCode(payload: SendSmsCodePayload) {
  const { data } = await http.post<ApiResponse<{ status: string }>>('/auth/sms/send-code', payload)
  return data.data
}

export async function smsLogin(payload: SmsLoginPayload) {
  const { data } = await http.post<ApiResponse<AuthMeResponse>>('/auth/sms/login', payload)
  return data.data
}

export async function accountLogin(payload: AccountLoginPayload) {
  const { data } = await http.post<ApiResponse<AuthMeResponse>>('/auth/account/login', payload)
  return data.data
}

export async function guestLogin() {
  const { data } = await http.post<ApiResponse<AuthMeResponse>>('/auth/guest/login')
  return data.data
}

export async function fetchMe() {
  const { data } = await http.get<ApiResponse<AuthMeResponse>>('/auth/me')
  return data.data
}

export async function logout() {
  const { data } = await http.post<ApiResponse<{ status: string }>>('/auth/logout')
  return data.data
}

export async function setPassword(payload: SetPasswordPayload) {
  const { data } = await http.post<ApiResponse<AuthMeResponse>>('/auth/password/set', payload)
  return data.data
}

export async function updateProfile(payload: UpdateProfilePayload) {
  const { data } = await http.put<ApiResponse<AuthMeResponse>>('/auth/profile', payload)
  return data.data
}

export async function updatePreferences(payload: UpdatePreferencesPayload) {
  const { data } = await http.put<ApiResponse<AuthMeResponse>>('/auth/preferences', payload)
  return data.data
}

export async function fetchSessions() {
  const { data } = await http.get<ApiResponse<AuthSessionRecord[]>>('/auth/sessions')
  return data.data
}

export async function revokeSession(sessionId: number) {
  const { data } = await http.post<ApiResponse<AuthSessionRecord>>(`/auth/sessions/${sessionId}/revoke`)
  return data.data
}

export async function searchUsers(keyword: string) {
  const { data } = await http.get<ApiResponse<UserSearchResult[]>>('/auth/users/search', {
    params: { keyword },
  })
  return data.data
}
