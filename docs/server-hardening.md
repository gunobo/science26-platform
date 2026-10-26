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
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' | sudo tee /etc/ssh/sshd_config.d/99-science26.conf
sudo sshd -t && sudo systemctl reload ssh
```

다시 새 창에서 키 로그인이 되는지 한 번 더 확인한다. 키 파일(`~/.ssh/id_ed25519`)을 잃어버리면 서버에 들어갈 수 없으니 백업해 둔다.

## 4. 관리자 계정

`ADMIN_EMAILS` 에 있는 구글 계정은 플랫폼 전체 권한을 가진다. 그 계정들에 구글 2단계 인증을 켠다.
