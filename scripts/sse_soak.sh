#!/usr/bin/env bash
# Long-running SSE soak test (default 8 hours). Requires a running HOLO-RTLS instance.
#
# Usage:
#   ./scripts/sse_soak.sh
#   SSE_SOAK_SECONDS=3600 HOLO_E2E_BASE=http://127.0.0.1:8080 ./scripts/sse_soak.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export HOLO_E2E_BASE="${HOLO_E2E_BASE:-http://127.0.0.1:8080}"
export SSE_SOAK_SECONDS="${SSE_SOAK_SECONDS:-28800}"
export HOLO_E2E_EMAIL="${HOLO_E2E_EMAIL:-admin@holo-rtls.local}"
export HOLO_E2E_PASSWORD="${HOLO_E2E_PASSWORD:-ChangeMe123!}"

python3 "$ROOT/scripts/sse_soak_runner.py"
