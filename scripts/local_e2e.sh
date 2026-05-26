#!/usr/bin/env bash
# Free common dev ports, start the API + Streamlit console, and run a smoke test.
#
# Usage:
#   ./scripts/local_e2e.sh              # free ports, start API + console, smoke test
#   ./scripts/local_e2e.sh --stop       # stop API/console and free ports
#   ./scripts/local_e2e.sh --no-smoke   # start API + console only
#   ./scripts/local_e2e.sh --no-console # start API only (no Streamlit)
#   ./scripts/local_e2e.sh --free-postgres   # also free localhost:5432
#
# Environment overrides:
#   LOCAL_E2E_PORT=8000
#   LOCAL_E2E_CONSOLE_PORT=8501
#   LOCAL_E2E_CONSOLE_DIR=/path/to/llm-evaluation-console
#   APP_AUTH_DEMO_SECRET=local-demo-secret

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_PARENT="$(cd "${REPO_ROOT}/.." && pwd)"
PID_FILE="${TMPDIR:-/tmp}/llm-evaluation-service-e2e.pid"
CONSOLE_PID_FILE="${TMPDIR:-/tmp}/llm-evaluation-console-e2e.pid"
LOG_FILE="${TMPDIR:-/tmp}/llm-evaluation-service-e2e.log"
CONSOLE_LOG_FILE="${TMPDIR:-/tmp}/llm-evaluation-console-e2e.log"
TOKEN_FILE="${TMPDIR:-/tmp}/llm-evaluation-service-e2e.token"

PORT="${LOCAL_E2E_PORT:-8000}"
CONSOLE_PORT="${LOCAL_E2E_CONSOLE_PORT:-8501}"
CONSOLE_ROOT="${LOCAL_E2E_CONSOLE_DIR:-${REPO_PARENT}/llm-evaluation-console}"
AUTH_SECRET="${APP_AUTH_DEMO_SECRET:-local-demo-secret}"
TENANT_ID="${LOCAL_E2E_TENANT_ID:-tenant-a}"
SUBJECT="${LOCAL_E2E_SUBJECT:-local-user}"
BASE_URL="http://127.0.0.1:${PORT}"
CONSOLE_URL="http://127.0.0.1:${CONSOLE_PORT}"

DEFAULT_PORTS=(8000 8501 8765 8877)
POSTGRES_PORT=5432

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

kill_listeners_on_port() {
  local port="$1"
  local pids=""
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  echo "Freeing port ${port} (PIDs: ${pids//$'\n'/ })"
  # shellcheck disable=SC2086
  kill -TERM ${pids} 2>/dev/null || true
  sleep 0.4
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  if [[ ! -f "${pid_file}" ]]; then
    return 0
  fi
  local old_pid=""
  old_pid="$(cat "${pid_file}")"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "Stopping previous ${label} process (PID ${old_pid})"
    kill -TERM "${old_pid}" 2>/dev/null || true
    sleep 0.4
    kill -9 "${old_pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}"
}

kill_stale_processes() {
  pkill -f "kubectl .*port-forward.*llm-evaluation-service" 2>/dev/null || true
  pkill -f "uvicorn app\\.main:app" 2>/dev/null || true
  pkill -f "streamlit run streamlit_app\\.py" 2>/dev/null || true
}

free_ports() {
  local include_postgres=false
  if [[ "${1:-}" == "with-postgres" ]]; then
    include_postgres=true
  fi

  kill_stale_processes
  for p in "${DEFAULT_PORTS[@]}"; do
    kill_listeners_on_port "${p}"
  done
  if [[ "${include_postgres}" == "true" ]]; then
    kill_listeners_on_port "${POSTGRES_PORT}"
  fi

  stop_pid_file "${PID_FILE}" "API"
  stop_pid_file "${CONSOLE_PID_FILE}" "console"
}

stop_all() {
  free_ports "${FREE_POSTGRES_FLAG:-}"
  rm -f "${TOKEN_FILE}"
  echo "Stopped local API, console, and freed dev ports."
}

wait_for_ready() {
  local attempts=40
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -sf "${BASE_URL}/health/ready" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "API did not become ready at ${BASE_URL}/health/ready" >&2
  echo "Last log lines:" >&2
  tail -20 "${LOG_FILE}" >&2 || true
  return 1
}

wait_for_console() {
  local attempts=40
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -sf "${CONSOLE_URL}/_stcore/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "Console did not become ready at ${CONSOLE_URL}" >&2
  echo "Last log lines:" >&2
  tail -20 "${CONSOLE_LOG_FILE}" >&2 || true
  return 1
}

create_demo_token() {
  cd "${REPO_ROOT}"
  APP_AUTH_DEMO_SECRET="${AUTH_SECRET}" \
    uv run python scripts/create_demo_jwt.py --tenant-id "${TENANT_ID}" --subject "${SUBJECT}"
}

start_api() {
  cd "${REPO_ROOT}"
  : >"${LOG_FILE}"
  echo "Starting API on ${BASE_URL} (log: ${LOG_FILE})"
  APP_STORAGE_BACKEND=memory \
    APP_AUTH_ENABLED=true \
    APP_AUTH_DEMO_SECRET="${AUTH_SECRET}" \
    APP_OTEL_EXPORTER=none \
    nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" >>"${LOG_FILE}" 2>&1 &
  echo $! >"${PID_FILE}"
  wait_for_ready
}

start_console() {
  if [[ ! -d "${CONSOLE_ROOT}" ]]; then
    echo "Console repo not found at ${CONSOLE_ROOT}; skipping Streamlit." >&2
    echo "Set LOCAL_E2E_CONSOLE_DIR to the llm-evaluation-console checkout." >&2
    START_CONSOLE=false
    return 0
  fi
  if [[ ! -f "${CONSOLE_ROOT}/streamlit_app.py" ]]; then
    echo "streamlit_app.py not found in ${CONSOLE_ROOT}; skipping Streamlit." >&2
    START_CONSOLE=false
    return 0
  fi

  cd "${CONSOLE_ROOT}"
  : >"${CONSOLE_LOG_FILE}"
  echo "Starting console on ${CONSOLE_URL} (log: ${CONSOLE_LOG_FILE})"
  LLM_EVALUATION_API_BASE_URL="${BASE_URL}" \
    nohup uv run --python 3.12 streamlit run streamlit_app.py \
      --server.headless true \
      --server.port "${CONSOLE_PORT}" \
      --server.address 127.0.0.1 \
      >>"${CONSOLE_LOG_FILE}" 2>&1 &
  echo $! >"${CONSOLE_PID_FILE}"
  wait_for_console
}

run_smoke_test() {
  local token="$1"
  local job_id status

  echo "=== health ==="
  curl -sf "${BASE_URL}/health/ready"
  echo

  echo "=== submit evaluation ==="
  local submit_resp
  submit_resp="$(
    curl -sf -X POST "${BASE_URL}/v1/evaluations" \
      -H "content-type: application/json" \
      -H "authorization: Bearer ${token}" \
      -d '{
        "project_id": "local-e2e",
        "question": "What should an LLM platform monitor?",
        "answer": "Failures, latency, cost, throughput, and quality.",
        "rubric": "Mention failures, latency, cost, or quality."
      }'
  )"
  echo "${submit_resp}"
  job_id="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['job_id'])" "${submit_resp}")"

  echo "=== poll job ${job_id} ==="
  local attempt resp
  for attempt in $(seq 1 20); do
    resp="$(curl -sf "${BASE_URL}/v1/evaluations/${job_id}" -H "authorization: Bearer ${token}")"
    status="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['status'])" "${resp}")"
    echo "attempt ${attempt}: ${status}"
    if [[ "${status}" == "succeeded" || "${status}" == "failed" ]]; then
      echo "${resp}" | python3 -m json.tool
      break
    fi
    sleep 0.3
  done

  if [[ "${status}" != "succeeded" ]]; then
    echo "Smoke test did not reach succeeded status." >&2
    return 1
  fi
}

print_urls() {
  local token="$1"
  echo
  echo "=== URLs ==="
  echo "Console UI: ${CONSOLE_URL}"
  echo "API docs:   ${BASE_URL}/docs"
  echo "Metrics:    ${BASE_URL}/metrics"
  echo
  echo "=== demo bearer token (paste into console sidebar, valid ~60m) ==="
  echo "${token}"
  echo "(also saved to ${TOKEN_FILE})"
  echo
  echo "Stop everything: ./scripts/local_e2e.sh --stop"
}

FREE_POSTGRES_FLAG=""
RUN_SMOKE=true
START_CONSOLE=true
MODE="start"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop)
      MODE="stop"
      shift
      ;;
    --no-smoke)
      RUN_SMOKE=false
      shift
      ;;
    --no-console)
      START_CONSOLE=false
      shift
      ;;
    --free-postgres)
      FREE_POSTGRES_FLAG="with-postgres"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${MODE}" == "stop" ]]; then
  stop_all
  exit 0
fi

free_ports "${FREE_POSTGRES_FLAG}"
start_api

token="$(create_demo_token)"
printf '%s\n' "${token}" >"${TOKEN_FILE}"

if [[ "${START_CONSOLE}" == "true" ]]; then
  start_console
fi

if [[ "${RUN_SMOKE}" == "true" ]]; then
  run_smoke_test "${token}"
  echo "Smoke test passed."
fi

print_urls "${token}"

if [[ -f "${PID_FILE}" ]]; then
  echo "API running (PID $(cat "${PID_FILE}"))."
fi
if [[ "${START_CONSOLE}" == "true" && -f "${CONSOLE_PID_FILE}" ]]; then
  echo "Console running (PID $(cat "${CONSOLE_PID_FILE}"))."
fi
