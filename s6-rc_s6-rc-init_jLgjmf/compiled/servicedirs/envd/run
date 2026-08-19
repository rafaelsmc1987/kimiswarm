#!/command/with-contenv bash
set -euo pipefail

# AGS 不是 firecracker 环境,没有 MMDS(169.254.169.254 丢包不可达):
# envd 默认会在 /init 校验和后台轮询里访问 MMDS,每次 /init 都先挂起数秒
# (10s client timeout 黑洞)才回落 first-time setup,是 create 耗时(实测 ~7s)
# 的主要构成。-isnotfc 让 envd 跳过一切 MMDS 行为,/init 立即可达。
for candidate in /usr/local/bin/envd /usr/bin/envd envd; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$(command -v "$candidate")" -isnotfc
  fi
done

echo "envd not found; Tencent E2B command execution will be unavailable" >&2
sleep infinity
