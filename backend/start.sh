#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Governed Data Platform — Single-Command Launcher
#  Lives inside governed-data-platform/ and starts both services.
#
#  Usage:
#    cd "/Users/ganeshshinde/Documents/Ellliot Systems/governed-data-platform"
#    ./start.sh
#
#  What it runs:
#    ┌──────────────────────────────────────────────────────────────┐
#    │  Flask Frontend + API    →  http://localhost:5001            │
#    │  FastAPI Backend (pure)  →  http://localhost:8000/docs       │
#    └──────────────────────────────────────────────────────────────┘
#
#  Press Ctrl+C to stop BOTH servers at the same time.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

# ── Resolve absolute paths ──────────────────────────────────────────────────
# This script lives inside governed-data-platform/
# Parent dir is "Ellliot Systems" which contains both projects.
FASTAPI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$FASTAPI_DIR")"
FLASK_DIR="$PARENT_DIR/flask-governed-api"

# ── Color codes ──────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║     Governed Data Platform — Starting All Services       ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  FastAPI dir : ${FASTAPI_DIR}"
echo -e "  Flask dir   : ${FLASK_DIR}"
echo ""

# ── PIDs so we can kill both on Ctrl+C ──────────────────────────────────────
PIDS=()

cleanup() {
    echo ""
    echo -e "${YELLOW}⏹  Stopping all services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo -e "${GREEN}✓  All services stopped. Goodbye.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Detect Python / uvicorn binaries ─────────────────────────────────────────
FLASK_VENV="$FLASK_DIR/venv"
FASTAPI_VENV="$FASTAPI_DIR/venv"

if [ -f "$FLASK_VENV/bin/python" ]; then
    FLASK_PYTHON="$FLASK_VENV/bin/python"
else
    FLASK_PYTHON="python3"
    echo -e "${YELLOW}⚠  Flask venv not found — using system python3${NC}"
fi

UVICORN_MODULE=""
if [ -f "$FASTAPI_VENV/bin/uvicorn" ]; then
    UVICORN_BIN="$FASTAPI_VENV/bin/uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN_BIN="uvicorn"
else
    UVICORN_BIN="$FASTAPI_VENV/bin/python"
    UVICORN_MODULE="-m uvicorn"
    echo -e "${YELLOW}⚠  uvicorn not found as standalone — running as python module${NC}"
fi

# ── Start Flask (Frontend + API) ─────────────────────────────────────────────
echo -e "${GREEN}▶  Starting Flask Frontend  →  http://localhost:5001${NC}"
(
    cd "$FLASK_DIR"
    if [ -f ".env" ]; then set -a; source .env; set +a; fi
    "$FLASK_PYTHON" app.py 2>&1 | sed 's/^/[FLASK]   /'
) &
PIDS+=($!)

sleep 1   # small stagger so startup logs don't interleave

# ── Start FastAPI (Backend API) ───────────────────────────────────────────────
echo -e "${BLUE}▶  Starting FastAPI Backend →  http://localhost:8000/docs${NC}"
(
    cd "$FASTAPI_DIR"
    if [ -f ".env" ]; then set -a; source .env; set +a; fi
    # shellcheck disable=SC2086
    "$UVICORN_BIN" $UVICORN_MODULE app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 \
        | sed 's/^/[FASTAPI] /'
) &
PIDS+=($!)

# ── Print access URLs ─────────────────────────────────────────────────────────
sleep 2
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  🌐  Flask Dashboard   →  ${GREEN}http://localhost:5001${NC}"
echo -e "${BOLD}  📡  FastAPI Docs      →  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "${BOLD}  🔍  FastAPI Redoc     →  ${BLUE}http://localhost:8000/redoc${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Press Ctrl+C to stop both servers${NC}"
echo ""

# ── Wait for both background processes ───────────────────────────────────────
wait
