#!/usr/bin/env bash
# 학생 컨테이너가 내부 대역(플랫폼·메타데이터 서버)에 접근하지 못하게 DOCKER-USER 체인에 규칙을 넣는다.
# 외부 인터넷은 허용. 서버 부팅 시 1회 실행.
set -euo pipefail
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16; do
  # 같은 도커 브리지 내부 통신(학생 → postgres/redis/traefik)은 ESTABLISHED 및 브리지 경유로 허용되고,
  # 호스트 바깥 사설 대역으로 나가는 트래픽만 막는다.
  iptables -C DOCKER-USER -o "$(ip route | awk '/default/ {print $5; exit}')" -d "$net" -j DROP 2>/dev/null \
    || iptables -I DOCKER-USER -o "$(ip route | awk '/default/ {print $5; exit}')" -d "$net" -j DROP
done
