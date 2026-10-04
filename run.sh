#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export SHADOWGATE_API_TOKENS="${SHADOWGATE_API_TOKENS:-{\"admin-token\":\"admin\",\"op-token\":\"operator\",\"view-token\":\"viewer\"}}"
export SHADOWGATE_DATA_DIR="${SHADOWGATE_DATA_DIR:-.shadowgate}"

if [[ "${1:-}" == "--check" ]]; then
  uv sync --extra dev
  uv run ruff check src tests
  uv run mypy
  uv run pytest -q
  exit 0
fi

uv sync --extra dev
echo "ShadowGate on http://127.0.0.1:8080  (dashboard: /ui)"
echo "tokens: admin-token / op-token / view-token"
echo "stop with Ctrl-C"
exec uv run uvicorn shadowgate.server.app:app --host 127.0.0.1 --port 8080
