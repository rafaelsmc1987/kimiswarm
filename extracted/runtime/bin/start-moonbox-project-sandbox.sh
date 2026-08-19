#!/usr/bin/env bash
set -euo pipefail

marker_dir="/opt/moonbox-project-template"
install -d -m 0755 "$marker_dir"
date -u +%Y-%m-%dT%H:%M:%SZ > "$marker_dir/container-started-at"

if [ ! -x /init ]; then
  echo "moonbox /init is missing; MOONBOX_BASE_IMAGE must be built from moonbox Dockerfile/Dockerfile.okc" >&2
  exit 1
fi

exec /init "$@"
