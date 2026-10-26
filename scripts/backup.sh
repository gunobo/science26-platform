#!/usr/bin/env bash
# PostgreSQL 전체 덤프를 NCP Object Storage(S3 호환)에 올리고 7일 지난 것은 지운다. cron 일 1회.
# 필요: aws CLI, 환경변수 NCP_ACCESS_KEY, NCP_SECRET_KEY, BACKUP_BUCKET
set -euo pipefail
ENDPOINT=https://kr.object.ncloudstorage.com
STAMP=$(date +%Y%m%d-%H%M)
FILE=/tmp/science26-$STAMP.sql.gz
docker exec s26-postgres pg_dumpall -U science26 | gzip > "$FILE"
export AWS_ACCESS_KEY_ID=$NCP_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$NCP_SECRET_KEY
aws --endpoint-url "$ENDPOINT" s3 cp "$FILE" "s3://$BACKUP_BUCKET/pg/"
rm -f "$FILE"
CUTOFF=$(date -d '7 days ago' +%Y%m%d)
aws --endpoint-url "$ENDPOINT" s3 ls "s3://$BACKUP_BUCKET/pg/" | awk '{print $4}' | while read -r f; do
  d=$(echo "$f" | sed -E 's/science26-([0-9]{8}).*/\1/')
  [[ "$d" < "$CUTOFF" ]] && aws --endpoint-url "$ENDPOINT" s3 rm "s3://$BACKUP_BUCKET/pg/$f"
done
