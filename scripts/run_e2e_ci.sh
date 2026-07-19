#!/usr/bin/env bash
# Start HOLO-RTLS and run Playwright smoke tests (used by GitHub Actions).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SECRET_KEY="${SECRET_KEY:-ci-secret-key-for-testing-only-32chars}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-ci-jwt-secret-key-for-testing-only-32chars}"
export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////tmp/holo_ci.db}"
export PLAYWRIGHT_E2E=1
export HOLO_E2E_BASE="${HOLO_E2E_BASE:-http://127.0.0.1:8080}"

python run.py &
APP_PID=$!

cleanup() {
  kill "$APP_PID" 2>/dev/null || true
  wait "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 60); do
  if curl -sf "${HOLO_E2E_BASE}/health" >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "ERROR: app process exited before /health was ready" >&2
    exit 1
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "ERROR: timed out waiting for ${HOLO_E2E_BASE}/health" >&2
  exit 1
fi

pytest tests/e2e/test_playwright_smoke.py -q
