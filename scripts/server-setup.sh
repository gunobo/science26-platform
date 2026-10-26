#!/usr/bin/env bash
# NCP 서버(Ubuntu 22.04/24.04) 초기 세팅. root 로 1회 실행한다.
#   sudo bash server-setup.sh /dev/xvdb      # 추가 Block Storage 장치 (lsblk 로 확인)
#
# 하는 일: Docker 설치, 추가 볼륨을 /data 에 마운트, 스왑 4GB, 저장소 클론(/opt/science26),
#          부팅 시 방화벽 규칙, 백업 cron 등록.
# 볼륨에 이미 파일시스템이 있으면 포맷하지 않는다.
set -euo pipefail

DEVICE="${1:-}"
REPO="https://github.com/gunobo/science26-platform.git"
APP_DIR=/opt/science26

[ "$(id -u)" = 0 ] || { echo "root 로 실행하세요 (sudo)"; exit 1; }

echo "== 패키지·Docker 설치"
apt-get update -y
apt-get install -y ca-certificates curl git awscli || apt-get install -y ca-certificates curl git
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# 기본 로그 크기 제한 (compose 에서 따로 지정하지 않은 컨테이너, BuildKit 컨테이너 등)
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' > /etc/docker/daemon.json
fi
systemctl enable --now docker

echo "== /data 볼륨"
mkdir -p /data
if [ -n "$DEVICE" ]; then
  if ! blkid "$DEVICE" >/dev/null 2>&1; then
    echo "$DEVICE 에 파일시스템이 없어 ext4 로 포맷합니다"
    mkfs.ext4 -F "$DEVICE"
  fi
  UUID=$(blkid -s UUID -o value "$DEVICE")
  grep -q "$UUID" /etc/fstab || echo "UUID=$UUID /data ext4 defaults,nofail 0 2" >> /etc/fstab
  mountpoint -q /data || mount /data
else
  echo "추가 볼륨 장치를 안 줘서 루트 디스크의 /data 를 씁니다"
fi
mkdir -p /data/postgres /data/redis /data/files /data/letsencrypt

echo "== 스왑 4GB"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "== 저장소"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO" "$APP_DIR"
fi

echo "== 부팅 시 방화벽 규칙 (학생 컨테이너 → 내부 대역 차단)"
cat > /etc/systemd/system/science26-firewall.service <<EOF
[Unit]
Description=science26 DOCKER-USER firewall rules
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash $APP_DIR/scripts/firewall.sh

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now science26-firewall.service

echo "== 백업 cron (매일 04:00, /etc/science26-backup.env 필요)"
cat > /etc/cron.d/science26-backup <<EOF
0 4 * * * root [ -f /etc/science26-backup.env ] && set -a && . /etc/science26-backup.env && set +a && /bin/bash $APP_DIR/scripts/backup.sh >> /var/log/science26-backup.log 2>&1
EOF

cat <<EOF

완료. 다음 단계:
  1) cd $APP_DIR && cp .env.example .env && ./scripts/gen-secrets.sh  → 출력값과 도메인·구글 OAuth 값을 .env 에 채우기
     (DATA_ROOT=/data, COOKIE_SECURE=true, ACME_EMAIL 필수)
  2) DNS: science26.bssm.dev, science26-upload.bssm.dev 의 A 레코드를 이 서버 공인 IP로
  3) docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
EOF
