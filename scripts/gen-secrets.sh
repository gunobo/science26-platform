#!/usr/bin/env bash
# .env 에 넣을 비밀값을 출력한다.
set -euo pipefail
rand() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }
echo "SECRET_KEY=$(rand)"
echo "ENV_ENCRYPTION_KEY=$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
echo "POSTGRES_PASSWORD=$(rand)"
echo "REDIS_PASSWORD=$(rand)"
