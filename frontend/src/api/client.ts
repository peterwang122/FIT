import axios from 'axios'

const timeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? '60000')

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1',
  timeout: Number.isFinite(timeoutMs) ? timeoutMs : 60000,
})
