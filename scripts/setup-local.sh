#!/usr/bin/env bash
# 로컬 개발용 환경 파일을 만든다 (이미 있으면 건드리지 않음). 비밀값은 화면에 출력하지 않는다.
# 접속: http://science26-upload.localhost:8080 (대시보드), http://science26.localhost:8080 (공개 목록)
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET=".env"
if [ -f "$TARGET" ]; then
  echo "$TARGET 이 이미 있어서 그대로 둡니다"
  exit 0
fi
{
  echo "PUBLIC_HOST=science26.localhost"
  echo "UPLOAD_HOST=science26-upload.localhost"
  echo "GOOGLE_CLIENT_ID="
  echo "GOOGLE_CLIENT_SECRET="
  echo "ALLOWED_GOOGLE_DOMAINS=bssm.hs.kr"
  echo "ADMIN_EMAILS=teacher@bssm.hs.kr"
  echo "COOKIE_SECURE=false"
  echo "DEV_LOGIN=true"
  ./scripts/gen-secrets.sh
  echo "DATA_ROOT=./data"
  echo "TRAEFIK_HTTP_PORT=8080"
} > "$TARGET"
chmod 600 "$TARGET"
echo "로컬 환경 파일을 만들었습니다"
