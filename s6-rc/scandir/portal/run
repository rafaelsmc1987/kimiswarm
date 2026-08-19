#!/command/with-contenv bash
set -euo pipefail

# Go portal overlay service (bind-token STS contract). Boots with an EMPTY
# mount manifest and -http-bind (:8080): kimiwarden delivers the identity at
# claim time — POST /api/v1/bind_token (warden-signed HS256 JWT that portal
# exchanges for scoped STS via kimiapi PortalService), then POST /api/v1/bind
# with the overlay manifest (skills/plugins/auth/vault). drive9 keeps the
# writable workspace at /mnt/agents; the reception preset init_script symlinks
# /app/.user/skills etc. into this mount when the overlay is enabled.

# kimiwarden injects the KIMI_PROJECT_PORTAL_CAPABILITY_* contract (enable flag,
# env, mount, gateway addrs). The reception preset still sets the legacy
# KIMI_PROJECT_PORTAL_OVERLAY=1 signal, so accept either as the enable gate.
if [ "${KIMI_PROJECT_PORTAL_CAPABILITY_ENABLED:-}" != "true" ] \
  && [ "${KIMI_PROJECT_PORTAL_OVERLAY:-}" != "1" ]; then
  echo "portal overlay disabled (no PORTAL_CAPABILITY_ENABLED / PORTAL_OVERLAY); staying idle" >&2
  exec sleep infinity
fi

if [ ! -x /usr/local/bin/portal ]; then
  echo "portal binary missing at /usr/local/bin/portal; overlay unavailable" >&2
  exec sleep infinity
fi

mount_point="${KIMI_PROJECT_PORTAL_CAPABILITY_MOUNT:-${KIMI_PORTAL_OVERLAY_MOUNT:-/mnt/portal-overlay}}"
install -d -m 0755 "$mount_point"

# Default to the test environment (dev gateway + DevConfig TOS).
env_flag="${KIMI_PROJECT_PORTAL_CAPABILITY_ENV:-${KIMI_PORTAL_ENV:-dev}}"

# Gateway endpoint overrides (PortalService). Empty means portal's built-in
# defaults, which are current: dev=https://kimi.kimi.team/apiv2,
# prod=https://kimi-api-sandbox.msh.team/apiv2.
gateway_args=()
if [ -n "${KIMI_PROJECT_PORTAL_CAPABILITY_DEV_ADDR:-}" ]; then
  gateway_args+=(-gateway-dev-addr "$KIMI_PROJECT_PORTAL_CAPABILITY_DEV_ADDR")
fi
if [ -n "${KIMI_PROJECT_PORTAL_CAPABILITY_PROD_ADDR:-}" ]; then
  gateway_args+=(-gateway-addr "$KIMI_PROJECT_PORTAL_CAPABILITY_PROD_ADDR")
fi

# Static K_OSS_* credentials are retired (the new portal fails closed on them);
# the TOS overlay is authorized by the claim-time bind-token STS exchange. No
# boot-time mounts are declared — the manifest arrives with the claim bind.
canary_args=()
if [ -n "${KIMI_CANARY:-}" ]; then
  canary_args+=(-canary "$KIMI_CANARY")
fi

exec /usr/local/bin/portal \
  -http-bind \
  -allow-other \
  -env "$env_flag" \
  "${gateway_args[@]}" \
  "${canary_args[@]}" \
  "$mount_point"
