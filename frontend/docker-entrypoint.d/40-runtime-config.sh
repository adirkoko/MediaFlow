#!/bin/sh
set -eu

: "${MEDIAFLOW_API_BASE:=/api}"

cat > /usr/share/nginx/html/js/runtime-config.js <<EOF
window.MEDIAFLOW_API_BASE = '${MEDIAFLOW_API_BASE}';
EOF
