# 서버 보안 점검

운영 서버에서 한 번씩 해야 하는 일. 순서대로 진행한다.

## 1. 보안 업데이트

학생 코드를 실행하는 서버라 커널·런타임 업데이트가 가장 중요한 방어다.

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades   # 보안 업데이트 매일 자동 설치
```

커널이 바뀌었으면(`/var/run/reboot-required` 가 있으면) 재부팅한다. 학생 빌드가 없는 시간에 한다.

```bash
[ -f /var/run/reboot-required ] && echo "재부팅 필요" || echo "재부팅 불필요"
sudo reboot
```

재부팅 후 플랫폼 컨테이너는 자동으로 뜨고, 워커가 시작하면서 실행 중이던 학생 스택을 다시 켠다. 방화벽 규칙도 부팅 때 다시 적용된다.

```bash
docker ps --filter name=s26- --format "table {{.Names}}\t{{.Status}}"
```

## 2. `.env` 비밀값 보관

DB 백업만으로는 복구가 안 된다. `ENV_ENCRYPTION_KEY` 가 없으면 학생 환경변수를 복호화할 수 없고, `SECRET_KEY` 가 바뀌면 학생 DB·Redis 비밀번호가 달라진다.
서버 밖 안전한 곳(비밀번호 관리자 등)에 보관한다. Object Storage 백업 버킷에 같이 두지 않는다.

맥에서:
```bash
scp root@<서버IP>:/opt/science26/.env ~/Desktop/science26.env
```
비밀번호 관리자의 보안 메모 같은 곳에 내용을 옮긴 뒤 파일은 지운다.

## 3. SSH 키 로그인으로 바꾸기

지금은 root 비밀번호 로그인이다. 키 로그인으로 바꾸고 비밀번호 로그인을 끈다.
**지금 접속한 SSH 창은 닫지 말고**, 새 창에서 키 로그인이 되는지 확인한 다음에 비밀번호를 끈다.

맥에서 키 만들기 (이미 `~/.ssh/id_ed25519` 가 있으면 건너뜀):
```bash
ssh-keygen -t ed25519 -C science26
```

서버에 공개키 등록 (마지막으로 비밀번호를 한 번 입력):
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@<서버IP>
```

새 터미널 창에서 비밀번호 없이 들어가지는지 확인:
```bash
ssh -i ~/.ssh/id_ed25519 root@<서버IP>
```

들어가지면, 서버에서 비밀번호 로그인 끄기:
```bash
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' | sudo tee /etc/ssh/sshd_config.d/00-science26.conf
sudo sshd -t && sudo systemctl reload ssh
sudo sshd -T | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) "
```

파일 이름은 `00-` 으로 시작해야 한다. sshd 는 `sshd_config.d` 의 파일을 이름 순으로 읽고 **먼저 나온 값**을 쓰는데,
Ubuntu 클라우드 이미지의 `50-cloud-init.conf` 에 `PasswordAuthentication yes` 가 있어서 뒤 순서 파일은 무시된다.
마지막 명령 결과가 `passwordauthentication no` 인지 확인한다.

다시 새 창에서 키 로그인이 되는지 한 번 더 확인한다. 키 파일(`~/.ssh/id_ed25519`)을 잃어버리면 서버에 들어갈 수 없으니 백업해 둔다.

## 4. 관리자 계정

`ADMIN_EMAILS` 에 있는 구글 계정은 플랫폼 전체 권한을 가진다. 그 계정들에 구글 2단계 인증을 켠다.

## 5. 장애 알림 (디스코드)

디스크 80%, 학생 DB 용량 초과, 컨테이너 비정상 종료 알림은 디스코드 웹훅으로만 간다. 설정하지 않으면 알림이 조용히 사라진다.

1. 디스코드 채널 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사
2. 서버에서 `.env` 의 `DISCORD_WEBHOOK_URL=` 에 붙여넣고 워커를 다시 띄운다
```bash
cd /opt/science26 && nano .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d worker
```
3. 테스트 알림:
```bash
docker exec s26-worker python -c "import asyncio; from app.worker import notify; asyncio.run(notify('알림 테스트'))"
```

## 6. 외부 상태 감시

서버가 통째로 죽으면 서버 안의 알림도 같이 멈춘다. 바깥에서 주기적으로 확인하는 무료 서비스(UptimeRobot, Better Stack 등)에 HTTP 감시를 건다.

- `https://science26-upload.bssm.dev/api/health` (200 이면 정상)
- `https://science26.bssm.dev/`
- 확인 간격 5분, 알림은 이메일 또는 디스코드

## 7. 학교 도메인 관리자에게 알릴 것

학생 페이지는 `science26.bssm.dev` 에서 학생이 작성한 코드를 그대로 실행한다. 브라우저 규칙상 이 페이지는 `bssm.dev` 전체에 쿠키를 심을 수 있다.
학교의 다른 `*.bssm.dev` 서비스는 로그인 쿠키에 `__Host-` 접두사를 쓰거나, 세션 쿠키를 신뢰하기 전에 출처를 확인해야 한다.
(이 플랫폼의 대시보드는 `__Host-s26_session` 을 써서 이 공격을 막는다.)
