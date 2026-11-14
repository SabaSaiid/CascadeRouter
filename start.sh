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

# Free ports 8000 and 5173 if lingering from previous runs
for port in 8000 5173; do
    occupied_pid=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$occupied_pid" ]; then
        echo -e "${YELLOW}[*] Port $port is in use (PID: $occupied_pid); freeing port...${NC}"
        kill -9 $occupied_pid 2>/dev/null || true
        sleep 0.3
    fi
done

# Cleanup on exit
PIDS=()
cleanup() {
    status=$?
    trap - EXIT INT TERM
    echo -e "\n${YELLOW}[*] Shutting down CascadeRouter services...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            pkill -P "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
        fi
    done
    for port in 8000 5173; do
        occupied_pid=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$occupied_pid" ]; then
            kill -9 $occupied_pid 2>/dev/null || true
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
        if [ ! -d "$ROOT_DIR/.venv" ] && [ ! -d "$ROOT_DIR/venv" ]; then
            echo -e "${CYAN}[*] Creating Python virtual environment in .venv...${NC}"
            "$PYTHON_CMD" -m venv "$ROOT_DIR/.venv"
            source "$ROOT_DIR/.venv/bin/activate"
            PYTHON_CMD="python"
        fi
        echo -e "${YELLOW}[*] Backend dependencies missing; installing from requirements.txt...${NC}"
        "$PYTHON_CMD" -m pip install -r "$ROOT_DIR/requirements.txt" || {
            echo -e "${YELLOW}[!] Note: Could not auto-install via pip. Proceeding with existing environment.${NC}"
        }
    fi

    if [ -n "$NEBIUS_API_KEY" ] && [[ ! "$NEBIUS_API_KEY" =~ ^your- ]]; then
        echo -e "${GREEN}[✓] Nebius Token Factory: Live cloud API enabled${NC}"
    else
        echo -e "${YELLOW}[i] Nebius Token Factory: Calibrated high-fidelity emulation active${NC}"
        echo -e "${YELLOW}[i] (For live cloud inference: export NEBIUS_API_KEY=\"<your-api-key>\")\n${NC}"
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
        echo -e "${CYAN}[*] Installing frontend dependencies via npm install...${NC}"
        npm install
    fi

    echo -e "${CYAN}[*] Starting CascadeRouter Vite Dev Server on http://localhost:5173...${NC}"
    echo -e "${GREEN}"
    echo -e "=================================================================="
    echo -e "  🚀 CascadeRouter IDE is launching!"
    echo -e "  👉 Opening your browser: http://localhost:5173"
    echo -e "=================================================================="
    echo -e "${NC}"

    npm run dev &
    FRONTEND_PID=$!
    PIDS+=("$FRONTEND_PID")

    # Automatically open the browser once the frontend server is listening
    (
        for i in {1..40}; do
            if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5173" 2>/dev/null | grep -q "200\|304"; then
                if command -v open >/dev/null 2>&1; then
                    open "http://localhost:5173"
                elif command -v xdg-open >/dev/null 2>&1; then
                    xdg-open "http://localhost:5173"
                fi
                break
            fi
            sleep 0.5
        done
    ) &

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
