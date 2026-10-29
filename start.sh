#!/usr/bin/env bash
# ==============================================================================
# CascadeRouter IDE — Startup Script
# ==============================================================================

set -e

# Terminal colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${PURPLE}"
cat << "EOF"
   ___                       _       ___             _            
  / __\__ _ ___  ___ __ _  __| | ___ / _ \___  _   _| |_ ___ _ __ 
 / /  / _` / __|/ __/ _` |/ _` |/ _ \ /_)/ _ \| | | | __/ _ \ '__|
/ /__| (_| \__ \ (_| (_| | (_| |  __/ _ \ (_) | |_| | ||  __/ |   
\____/\__,_|___/\___\__,_|\__,_|\___\/ \_\___/ \__,_|\__\___|_|   
      Autonomous FinOps & Latency Compiler for LLM Architectures
EOF
echo -e "${NC}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Configuration is explicit; never create or load a dotenv file.
BACKEND_ARGS=()
EXPLICIT_CONFIG=0
if [ "$#" -gt 0 ]; then
    if [ "$#" -ne 2 ] || [ "$1" != "--backend-config" ]; then
        echo 'Usage: bash start.sh [--backend-config ABSOLUTE_NON_SECRET_JSON]'
        exit 2
    fi
    BACKEND_ARGS=(--config "$2")
    EXPLICIT_CONFIG=1
fi

# Cleanup on exit
PIDS=()
cleanup() {
    status=$?
    trap - EXIT INT TERM
    echo -e "\n${YELLOW}[*] Shutting down CascadeRouter services...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo -e "${GREEN}[✓] Shutdown complete. Goodbye!${NC}"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 2. Check & Start Backend (if available)
if [ -f "$ROOT_DIR/backend/main.py" ]; then
    if [ -d "$ROOT_DIR/venv" ]; then
        source "$ROOT_DIR/venv/bin/activate"
    elif [ -d "$ROOT_DIR/.venv" ]; then
        source "$ROOT_DIR/.venv/bin/activate"
    fi

    PYTHON_CMD=""
    if command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    else
        echo -e "${YELLOW}[!] Error: Neither python nor python3 found in PATH.${NC}"
        exit 1
    fi

    if ! "$PYTHON_CMD" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] Warning: Backend dependencies (fastapi, uvicorn) not found for $PYTHON_CMD.${NC}"
        echo -e "${YELLOW}[!] Install them using: pip install -r requirements.txt${NC}"
    fi

    if [ "$EXPLICIT_CONFIG" -eq 0 ]; then
        echo -e "${CYAN}[*] Auto-provisioning local benchmark registry, pricing & permitted roots...${NC}"
        AUTO_CONFIG=$("$PYTHON_CMD" -B -m backend.services.default_assets "$ROOT_DIR")
        BACKEND_ARGS=(--config "$AUTO_CONFIG")
        echo -e "${GREEN}[✓] Local sandbox ready: $AUTO_CONFIG${NC}"
    fi

    echo -e "${CYAN}[*] Starting FastAPI Backend on http://localhost:8000...${NC}"
    "$PYTHON_CMD" -B -m backend.main "${BACKEND_ARGS[@]}" &
    BACKEND_PID=$!
    PIDS+=("$BACKEND_PID")
    echo -e "${GREEN}[✓] Backend service launched (PID: $BACKEND_PID)${NC}"
else
    echo -e "${YELLOW}[i] Backend entrypoint (backend/main.py) not present yet.${NC}"
    echo -e "${YELLOW}[i] Frontend will use Mock / Recorded telemetry layer.${NC}"
fi

# 3. Check & Start Frontend
if [ -d "$ROOT_DIR/frontend" ]; then
    echo -e "${CYAN}[*] Checking frontend dependencies...${NC}"
    cd "$ROOT_DIR/frontend"

    if [ ! -d "node_modules" ]; then
        echo 'Frontend dependencies are absent. Install them explicitly before using start.sh.'
        exit 1
    fi

    echo -e "${CYAN}[*] Starting CascadeRouter Vite Dev Server on http://localhost:5173...${NC}"
    echo -e "${GREEN}"
    echo -e "=================================================================="
    echo -e "  🚀 CascadeRouter IDE is launching!"
    echo -e "  👉 Open your browser: http://localhost:5173"
    echo -e "=================================================================="
    echo -e "${NC}"

    npm run dev &
    FRONTEND_PID=$!
    PIDS+=("$FRONTEND_PID")

    # Wait for child processes
    # Bash 4.3+: wait -n propagates either service's failure and stops its sibling.
    # Bash < 4.3 (such as macOS default /bin/bash): monitor processes periodically.
    if (( BASH_VERSINFO[0] > 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 3) )); then
        wait -n "${PIDS[@]}"
    else
        while true; do
            for pid in "${PIDS[@]}"; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break 2
                fi
            done
            sleep 1
        done
    fi
else
    echo -e "${YELLOW}[!] Error: frontend directory not found.${NC}"
    exit 1
fi
