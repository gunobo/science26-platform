#!/bin/sh
# ACL 파일이 없으면 default 사용자만 넣어 만든다. 학생 사용자는 워커가 ACL SETUSER 후 ACL SAVE 한다.
set -e
ACL=/data/users.acl
if [ ! -f "$ACL" ]; then
  echo "user default on >${REDIS_PASSWORD} ~* &* +@all" > "$ACL"
fi
exec redis-server --appendonly yes --aclfile "$ACL" --maxmemory 1gb --maxmemory-policy noeviction
