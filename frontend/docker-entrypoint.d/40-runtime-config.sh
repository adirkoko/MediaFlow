#!/bin/sh
set -eu

: "${MEDIAFLOW_API_BASE:=/api}"
: "${MEDIAFLOW_PUBLIC_URL:=}"

MEDIAFLOW_PUBLIC_URL="${MEDIAFLOW_PUBLIC_URL%/}"

cat > /usr/share/nginx/html/js/runtime-config.js <<EOF
window.MEDIAFLOW_API_BASE = '${MEDIAFLOW_API_BASE}';
EOF

sed -i "s|__MEDIAFLOW_PUBLIC_URL__|${MEDIAFLOW_PUBLIC_URL}|g" /usr/share/nginx/html/index.html
