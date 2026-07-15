#!/usr/bin/env bash
# =====================================================================
# conversation-core · Launch script (slim / Phase 3 Stage 5)
#
# Assumes: .env already exists (key collection & writing hosted by AI;
#          or developer runs `python scripts/setup-credentials.py` as fallback).
# Does only four things:
#   1. Detect Python ≥ 3.9
#   2. Create / reuse venv (does not pollute global environment)
#   3. Install / verify dependencies (Tsinghua mirror first, fallback to official source)
#   4. Launch FastAPI uvicorn (HTTP; --https uses self-signed cert)
#
# Usage:
#   ./start.sh                  # HTTP launch (default port 3000)
#   ./start.sh --https          # HTTPS launch (self-signed)
#   ./start.sh --rebuild        # Force venv rebuild
#   ./start.sh --port 8080      # Custom port
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CORE_DIR="$SCRIPT_DIR/capabilities/conversation-core"
ENV_FILE="$CORE_DIR/.env"
REQUIREMENTS="$CORE_DIR/requirements.txt"
VENV_DIR="$SCRIPT_DIR/.venv"
MIN_PY_MAJOR=3; MIN_PY_MINOR=9
PORT=3000; REBUILD=0; USE_HTTPS=0

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else GREEN=''; YELLOW=''; RED=''; CYAN=''; BOLD=''; NC=''; fi
log()  { printf "${CYAN}[%s]${NC} %s\n" "$(date +%H:%M:%S)" "$*"; }
ok()   { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC}  %s\n" "$*"; }
die()  { printf "${RED}✗${NC} %s\n" "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --rebuild) REBUILD=1 ;;
        --https)   USE_HTTPS=1 ;;
        --port)    shift; PORT="$1" ;;
        --help|-h) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "Ignoring unknown argument: $1" ;;
    esac
    shift
done

# ---------------- Step 1: Prerequisites ----------------
[ -f "$ENV_FILE" ] || die ".env not found: $ENV_FILE\n  Please first complete the 3-key configuration in the Coding Agent per SKILL.md §7;\n  or developer fallback: python3 scripts/setup-credentials.py"

PY_CMD=""
for cand in python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        VER=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        MAJOR=$(echo "$VER" | cut -d. -f1); MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -gt "$MIN_PY_MAJOR" ] || { [ "$MAJOR" -eq "$MIN_PY_MAJOR" ] && [ "$MINOR" -ge "$MIN_PY_MINOR" ]; }; then
            PY_CMD="$cand"; ok "Python $VER -> $(command -v "$cand")"; break
        fi
    fi
done
[ -z "$PY_CMD" ] && die "No Python ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR} detected"

# ---------------- Step 2: venv ----------------
[ "$REBUILD" -eq 1 ] && [ -d "$VENV_DIR" ] && { warn "Rebuilding venv..."; rm -rf "$VENV_DIR"; }
NEED_INSTALL=0
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment..."
    "$PY_CMD" -m venv "$VENV_DIR" || die "venv creation failed (Linux may need: apt install python3-venv)"
    NEED_INSTALL=1
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
VENV_PY="$VENV_DIR/bin/python"; VENV_PIP="$VENV_DIR/bin/pip"

# ---------------- Step 3: Dependencies ----------------
[ "$NEED_INSTALL" -eq 0 ] && ! "$VENV_PY" -c "import fastapi, uvicorn, requests, dotenv, pydantic" 2>/dev/null && NEED_INSTALL=1
if [ "$NEED_INSTALL" -eq 1 ]; then
    log "Installing dependencies..."
    "$VENV_PIP" install --upgrade pip >/dev/null 2>&1 || true
    if "$VENV_PIP" install -r "$REQUIREMENTS" -i "https://pypi.tuna.tsinghua.edu.cn/simple" --timeout 15 >/dev/null 2>&1; then
        ok "Dependencies installed (Tsinghua mirror)"
    else
        warn "Mirror source failed, switching to official source..."
        "$VENV_PIP" install -r "$REQUIREMENTS" >/dev/null || die "Dependency installation failed"
        ok "Dependencies installed (official source)"
    fi
else ok "Dependencies ready"; fi

# ---------------- Step 4: Launch ----------------
SSL_ARGS=""
if [ "$USE_HTTPS" -eq 1 ]; then
    CERT_DIR="$SCRIPT_DIR/certs"; CERT_FILE="$CERT_DIR/cert.pem"; KEY_FILE="$CERT_DIR/key.pem"
    if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        command -v openssl >/dev/null 2>&1 || die "openssl not installed"
        mkdir -p "$CERT_DIR"
        openssl req -x509 -newkey rsa:2048 -nodes -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -days 365 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
        ok "Self-signed certificate generated"
    fi
    SSL_ARGS="--ssl-keyfile $KEY_FILE --ssl-certfile $CERT_FILE"
fi

SCHEME="http"; [ "$USE_HTTPS" -eq 1 ] && SCHEME="https"
printf "%b🚀 Launching conversation-core: %s://localhost:%s%b (Ctrl+C to stop)\n" "$GREEN" "$SCHEME" "$PORT" "$NC"

cd "$CORE_DIR"
export HOST="${HOST:-0.0.0.0}"; export PORT="$PORT"
# shellcheck disable=SC2086
exec "$VENV_PY" -m uvicorn src.server:app --host "$HOST" --port "$PORT" $SSL_ARGS
