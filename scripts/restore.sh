#!/usr/bin/env bash
# Object Storage 의 백업으로 PostgreSQL 을 되돌린다. 현재 DB 는 지우지 않고 옆으로 옮겨 둔다.
#   sudo bash scripts/restore.sh            # 백업 목록만 보기
#   sudo bash scripts/restore.sh <파일명>    # 그 백업으로 복구 (확인 입력 필요)
#
# 복구하는 동안 대시보드·빌드가 멈춘다. 학생 페이지(이미 떠 있는 컨테이너)는 DB 를 쓰는 풀스택만 잠시 오류가 난다.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=${ENV_FILE:-/etc/science26-backup.env}
set -a; . "$ENV_FILE"; set +a
# .env 는 셸 문법이 아니라서(공백 포함 값) 필요한 값만 꺼낸다
DATA_ROOT=$(grep -E '^DATA_ROOT=' .env | cut -d= -f2- || true)
ENDPOINT=${BACKUP_ENDPOINT:-https://kr.object.ncloudstorage.com}
AWS_IMAGE=amazon/aws-cli:2.38.1
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
PGDATA_DIR=${DATA_ROOT:-./data}/postgres

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
s3() {
  docker run --rm --env-file "$ENV_FILE" \
    -e AWS_DEFAULT_REGION="${BACKUP_REGION:-kr-standard}" \
    -e AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    -e AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    -v "$WORK:/work" -w /work "$AWS_IMAGE" --endpoint-url "$ENDPOINT" s3 "$@"
}

if [ $# -eq 0 ]; then
  echo "백업 목록 (s3://$BACKUP_BUCKET/pg/):"
  s3 ls "s3://$BACKUP_BUCKET/pg/"
  echo
  echo "복구: sudo bash scripts/restore.sh <파일명>"
  exit 0
fi

FILE=$1
s3 cp "s3://$BACKUP_BUCKET/pg/$FILE" "$FILE" --only-show-errors
gzip -t "$WORK/$FILE"

echo "주의: 지금 DB 를 $FILE 시점으로 되돌립니다. 그 이후의 업로드 기록·학생 DB 데이터는 사라집니다."
echo "      현재 DB 폴더는 지우지 않고 ${PGDATA_DIR}.before-restore-<시각> 으로 옮겨 둡니다."
read -r -p "계속하려면 '복구' 라고 입력하세요: " answer
[ "$answer" = "복구" ] || { echo "취소했습니다"; exit 1; }

$COMPOSE stop worker api postgres
BACKUP_DIR="${PGDATA_DIR}.before-restore-$(date +%Y%m%d-%H%M%S)"
mv "$PGDATA_DIR" "$BACKUP_DIR"
$COMPOSE up -d postgres
until docker exec s26-postgres pg_isready -U science26 >/dev/null 2>&1; do sleep 2; done
sleep 3
# 새로 초기화된 클러스터에 덤프를 붓는다. science26 역할·DB 가 이미 있다는 오류는 무시해도 된다.
gunzip -c "$WORK/$FILE" | docker exec -i s26-postgres psql -q -U science26 -d postgres >/dev/null 2>"$WORK/restore.log" || true
grep -vE "already exists" "$WORK/restore.log" | head -20 || true
$COMPOSE up -d
echo "복구 완료. 이전 DB 폴더: $BACKUP_DIR (확인 후 지워도 됨)"
