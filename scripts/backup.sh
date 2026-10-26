#!/usr/bin/env bash
# PostgreSQL 전체 덤프(플랫폼 + 학생 DB)를 NCP Object Storage 에 올리고, 보관 기간이 지난 것은 지운다.
# cron 으로 하루 1번 (server-setup.sh 가 등록). 직접 실행해서 확인할 수도 있다: sudo bash scripts/backup.sh
#
# 설정 파일 /etc/science26-backup.env (chmod 600):
#   AWS_ACCESS_KEY_ID=...        NCP API 인증키 (Access Key ID)
#   AWS_SECRET_ACCESS_KEY=...    NCP API 인증키 (Secret Key)
#   BACKUP_BUCKET=science26-backup
#   BACKUP_KEEP_DAYS=7           (선택)
#
# aws CLI 는 서버에 설치하지 않고 공식 Docker 이미지로 실행한다 (Ubuntu 24.04 에는 apt 패키지가 없음).
set -euo pipefail

ENV_FILE=${ENV_FILE:-/etc/science26-backup.env}
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE 이 없습니다 (docs/backup.md 참고)"; exit 1; }
set -a; . "$ENV_FILE"; set +a
: "${BACKUP_BUCKET:?BACKUP_BUCKET 이 필요합니다}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID 가 필요합니다}"
KEEP_DAYS=${BACKUP_KEEP_DAYS:-7}
ENDPOINT=${BACKUP_ENDPOINT:-https://kr.object.ncloudstorage.com}
AWS_IMAGE=amazon/aws-cli:2.38.1

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# 인증키는 명령줄이 아니라 --env-file 로 넘겨서 프로세스 목록에 남지 않게 한다
s3() {
  docker run --rm --env-file "$ENV_FILE" \
    -e AWS_DEFAULT_REGION="${BACKUP_REGION:-kr-standard}" \
    -e AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    -e AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    -v "$WORK:/work" -w /work "$AWS_IMAGE" --endpoint-url "$ENDPOINT" s3 "$@"
}

FILE=science26-$(date +%Y%m%d-%H%M).sql.gz
docker exec s26-postgres pg_dumpall -U science26 | gzip > "$WORK/$FILE"
SIZE=$(stat -c%s "$WORK/$FILE")
if [ "$SIZE" -lt 1000 ]; then
  echo "덤프가 비정상적으로 작습니다 (${SIZE}B). 업로드하지 않습니다"
  exit 1
fi

s3 cp "$FILE" "s3://$BACKUP_BUCKET/pg/$FILE" --only-show-errors
echo "업로드: s3://$BACKUP_BUCKET/pg/$FILE ($(numfmt --to=iec "$SIZE"))"

CUTOFF=$(date -d "$KEEP_DAYS days ago" +%Y%m%d)
s3 ls "s3://$BACKUP_BUCKET/pg/" | awk '{print $4}' | while read -r f; do
  d=$(sed -nE 's/^science26-([0-9]{8})-.*/\1/p' <<<"$f")
  if [ -n "$d" ] && [[ "$d" < "$CUTOFF" ]]; then
    s3 rm "s3://$BACKUP_BUCKET/pg/$f" --only-show-errors
    echo "보관 기간 지남, 삭제: $f"
  fi
done
echo "백업 완료"
