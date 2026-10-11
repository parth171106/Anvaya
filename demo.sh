#!/usr/bin/env bash
# Reset ANVAYA to the first frame of the demo script. Usage: ./demo.sh [--speed 10|20|40] [--no-llm]
set -euo pipefail
SPEED=20
USE_LLM=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --speed) SPEED="$2"; shift 2 ;;
    --no-llm) USE_LLM=0; shift ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done
if [[ "$SPEED" != "10" && "$SPEED" != "20" && "$SPEED" != "40" ]]; then
  echo "Speed must be 10, 20 or 40"; exit 2
fi

API="http://localhost:8000/api"
PY=""
for c in python3 python; do   # the first one that actually runs (Windows ships a python3 store stub)
  if "$c" -c "" >/dev/null 2>&1; then PY="$c"; break; fi
done
[[ -n "$PY" ]] || { echo "Python 3 is required for demo.sh"; exit 1; }
json() { "$PY" -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

running() { docker compose ps --status running --services 2>/dev/null | grep -qx "$1"; }

# 1. If the stack isn't running, check the ports are free and start it.
if ! running api; then
  for p in 8000 8080; do
    if (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null; then
      echo "Port $p is already in use by another program. Free it and run ./demo.sh again."; exit 1
    fi
  done
  if [[ "$USE_LLM" == "1" ]]; then
    docker compose --profile llm up -d
  else
    docker compose up -d
  fi
elif [[ "$USE_LLM" == "1" ]] && ! running ollama; then
  docker compose --profile llm up -d ollama
fi

# 2. Wait for the API to be healthy (60 s max).
for i in $(seq 1 60); do
  if curl -fsS "$API/health" >/dev/null 2>&1; then break; fi
  sleep 1
  if [[ "$i" == "60" ]]; then echo "API did not become healthy. Run: docker compose logs api"; exit 1; fi
done

# 3. Reset everything and set the speed.
curl -fsS -X POST "$API/demo/reset" >/dev/null || { echo "Reset failed. Run: docker compose restart api"; exit 1; }
curl -fsS -X POST "$API/demo/speed" -H 'Content-Type: application/json' -d "{\"speed\": $SPEED}" >/dev/null

# 4. Confirm the clean state.
for i in $(seq 1 30); do
  RAW=$(curl -fsS "$API/stats" | json "d['raw_total']")
  [[ "$RAW" == "0" ]] && break
  sleep 0.5
done
if [[ "$RAW" != "0" ]]; then echo "State not clean (raw_total=$RAW). Run ./demo.sh again."; exit 1; fi

# 5. Report the health chips the video depends on.
HEALTH=$(curl -fsS "$API/health")
LLM=$(echo "$HEALTH" | json "d['components']['llm']['status']")
NET=$(echo "$HEALTH" | json "d['components']['network']['status']")
echo "Local LLM: $LLM   Network: $NET   Speed: ${SPEED}x"
[[ "$LLM" != "ready" ]] && echo "Note: Search will use query templates — use the alternate narration lines."
[[ "$NET" == "external_route" ]] && echo "Warning: this machine has an external route. Turn Wi-Fi off for the offline shots."
echo "ANVAYA ready · open http://localhost:8080/overview"
