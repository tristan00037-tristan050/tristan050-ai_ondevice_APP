#!/usr/bin/env bash
set -euo pipefail

# macOS 기준: lsof 기반
port_pids() {
  local port="$1"
  lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
}

# 포트 점유 PID + (필요 시) 부모(node/npm/npx/tsx/nodemon)까지 정리
free_port_strict() {
  local port="$1"
  local pids
  pids="$(port_pids "${port}")"

  if [ -z "${pids}" ]; then
    echo "[ports] ${port} is free"
    return 0
  fi

  echo "[ports] Found LISTEN PID(s) on ${port}: ${pids}"

  local kill_list=""
  for pid in ${pids}; do
    kill_list="${kill_list} ${pid}"

    # 부모까지 정리(부모가 dev watcher일 가능성 차단)
    local ppid pcomm
    ppid="$(ps -o ppid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
    if [ -n "${ppid}" ] && [ "${ppid}" != "1" ]; then
      pcomm="$(ps -o comm= -p "${ppid}" 2>/dev/null | tr -d ' ' || true)"
      case "${pcomm}" in
        node|npm|npx|tsx|nodemon|pnpm|yarn)
          kill_list="${kill_list} ${ppid}"
          ;;
        *)
          ;;
      esac
    fi
  done

  # 중복 제거
  kill_list="$(echo "${kill_list}" | tr ' ' '\n' | awk 'NF' | sort -u | tr '\n' ' ')"

  echo "[ports] Killing PID(s): ${kill_list}"
  kill -15 ${kill_list} 2>/dev/null || true
  sleep 2
  
  # 여전히 살아있는 프로세스 강제 종료
  local remaining
  remaining="$(port_pids "${port}")"
  if [ -n "${remaining}" ]; then
    echo "[ports] Force killing remaining PID(s): ${remaining}"
    kill -9 ${remaining} 2>/dev/null || true
    sleep 1
  fi
  
  # 최종 확인 및 강제 정리
  remaining="$(port_pids "${port}")"
  if [ -n "${remaining}" ]; then
    echo "[ports] WARNING: ${port} still in use, attempting final cleanup..."
    # 모든 node 프로세스 중 8081 포트를 사용하는 것 강제 종료
    lsof -nP -tiTCP:"${port}" -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
    sleep 1
    
    # 최종 재확인
    remaining="$(port_pids "${port}")"
    if [ -n "${remaining}" ]; then
      echo "[ports] ERROR: ${port} is still in use after cleanup"
      lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
      return 1
    fi
  fi

  echo "[ports] ${port} is free"
}

# healthz가 살아 있으면 재기동 금지(중복 실행 방지)
bff_is_healthy() {
  curl -fsS --max-time 1 http://localhost:8081/healthz >/dev/null 2>&1
}

