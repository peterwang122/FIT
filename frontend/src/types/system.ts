export interface PhddnsWatchdogStatus {
  installed: boolean
  enabled: boolean
  running: boolean
  pid: number | null
  last_exit_status: number | null
  label: string
  plist_path: string
  log_lines: string[]
  message: string
}

export interface PhddnsWatchdogTogglePayload {
  enabled: boolean
}
