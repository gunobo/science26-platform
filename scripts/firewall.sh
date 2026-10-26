#!/usr/bin/env bash
# 컨테이너가 호스트 바깥 사설 대역(VPC 내부 서버·메타데이터 서버)에 접근하지 못하게 한다.
# 외부 인터넷과, 호스트가 쓰는 DNS 서버(NCP는 사설 IP)로의 질의는 허용. 부팅 시마다 다시 실행해도 된다.
set -euo pipefail

CHAIN=S26-EGRESS
IFACE=$(ip route | awk '/default/ {print $5; exit}')

# systemd-resolved 를 쓰면 실제 상위 DNS 는 /run/systemd/resolve/resolv.conf 에 있다 (Docker 도 이걸 쓴다).
RESOLV=/etc/resolv.conf
[ -f /run/systemd/resolve/resolv.conf ] && RESOLV=/run/systemd/resolve/resolv.conf
NAMESERVERS=$(awk '/^nameserver/ && $2 !~ /^127\./ && $2 !~ /:/ {print $2}' "$RESOLV")

iptables -N "$CHAIN" 2>/dev/null || iptables -F "$CHAIN"
iptables -C DOCKER-USER -j "$CHAIN" 2>/dev/null || iptables -I DOCKER-USER -j "$CHAIN"

# 예전 버전이 DOCKER-USER 에 직접 넣은 DROP 규칙 제거
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16; do
  while iptables -D DOCKER-USER -o "$IFACE" -d "$net" -j DROP 2>/dev/null; do :; done
done

iptables -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for ns in $NAMESERVERS; do
  iptables -A "$CHAIN" -o "$IFACE" -d "$ns" -p udp --dport 53 -j RETURN
  iptables -A "$CHAIN" -o "$IFACE" -d "$ns" -p tcp --dport 53 -j RETURN
done
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16; do
  iptables -A "$CHAIN" -o "$IFACE" -d "$net" -j DROP
done
iptables -A "$CHAIN" -j RETURN

# 컨테이너 → 서버 자신(도커 브리지 게이트웨이)으로 들어오는 SSH 차단.
# 위 규칙은 서버 밖으로 나가는 트래픽만 다루고, ACG 도 서버 내부 트래픽에는 적용되지 않는다.
IN_CHAIN=S26-HOST-IN
iptables -N "$IN_CHAIN" 2>/dev/null || iptables -F "$IN_CHAIN"
for ifc in docker0 br+; do
  iptables -C INPUT -i "$ifc" -j "$IN_CHAIN" 2>/dev/null || iptables -I INPUT -i "$ifc" -j "$IN_CHAIN"
done
iptables -A "$IN_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A "$IN_CHAIN" -p tcp --dport 22 -j DROP
iptables -A "$IN_CHAIN" -j RETURN

echo "DNS 허용: ${NAMESERVERS:-없음}"
echo "컨테이너 → 호스트 SSH 차단 적용"
