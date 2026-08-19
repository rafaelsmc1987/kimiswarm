#!/command/with-contenv bash
set -euo pipefail
/command/s6-svwait -u /run/service/kasmvnc
cd /app
export DISPLAY=:99
export XAUTHORITY=/home/kimi/.Xauthority
export HOME=/home/kimi
export PWD=/app
export PATH=/command:/home/kimi/.local/bin:/home/kimi/.npm-global/bin:${PATH}
export NODE_PATH=/home/kimi/.npm-global/lib/node_modules
exec /command/s6-setuidgid kimi python3 /app/browser_guard.py --wait-display --display "${DISPLAY}" --timeout 60 --monitor
