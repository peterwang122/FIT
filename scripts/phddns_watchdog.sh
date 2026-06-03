#!/bin/zsh
set -u

LOG_FILE="/tmp/fit-phddns-watchdog.log"
STATE_FILE="/tmp/fit-phddns-watchdog.failcount"
LOCAL_URL="http://127.0.0.1:5173/"
PUBLIC_URL="https://661jlgb50275.vicp.fun/"
APP_NAME="花生壳"

log() {
  /bin/echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

get_fail_count() {
  if [[ -f "$STATE_FILE" ]]; then
    /bin/cat "$STATE_FILE" 2>/dev/null
  else
    /bin/echo 0
  fi
}

set_fail_count() {
  /bin/echo "$1" > "$STATE_FILE"
}

restart_phddns() {
  log "Restarting ${APP_NAME}"
  /usr/bin/osascript -e "tell application \"${APP_NAME}\" to quit" >/dev/null 2>&1 || true
  /bin/sleep 8
  /usr/bin/pkill -f "/Applications/${APP_NAME}.app/Contents/MacOS/PhDDNS" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "/Applications/${APP_NAME}.app/Contents/XPCServices/PhtunnelService.xpc/Contents/MacOS/PhtunnelService" >/dev/null 2>&1 || true
  /bin/sleep 3
  /usr/bin/open -a "$APP_NAME"
  /bin/sleep 20
}

if ! /usr/bin/nc -z 127.0.0.1 5173 >/dev/null 2>&1; then
  log "Local FIT frontend is unavailable at ${LOCAL_URL}; skip PhDDNS restart"
  exit 0
fi

if ! /usr/bin/pgrep -f "/Applications/${APP_NAME}.app/Contents/MacOS/PhDDNS" >/dev/null 2>&1 \
  || ! /usr/bin/pgrep -f "/Applications/${APP_NAME}.app/Contents/XPCServices/PhtunnelService.xpc/Contents/MacOS/PhtunnelService" >/dev/null 2>&1; then
  log "PhDDNS process missing"
  restart_phddns
  set_fail_count 0
  exit 0
fi

if /usr/bin/curl --noproxy '*' -k -fsS -I --connect-timeout 10 --max-time 20 "$PUBLIC_URL" >/dev/null 2>&1; then
  set_fail_count 0
  log "OK ${PUBLIC_URL}"
  exit 0
fi

fail_count="$(get_fail_count)"
if ! [[ "$fail_count" =~ '^[0-9]+$' ]]; then
  fail_count=0
fi
fail_count=$((fail_count + 1))
set_fail_count "$fail_count"
log "Public URL check failed (${fail_count}/2): ${PUBLIC_URL}"

if (( fail_count >= 2 )); then
  restart_phddns
  if /usr/bin/curl --noproxy '*' -k -fsS -I --connect-timeout 10 --max-time 20 "$PUBLIC_URL" >/dev/null 2>&1; then
    log "Recovered after restart"
    set_fail_count 0
  else
    log "Still unavailable after restart"
    set_fail_count 2
  fi
fi
