# 백업 설정

매일 04:00 에 PostgreSQL 전체(플랫폼 + 학생 DB)를 덤프해서 NCP Object Storage 에 올리고, 7일 지난 백업은 지운다.
업로드 원본·학생 이미지는 백업하지 않는다 (학생이 다시 올리면 되고, 용량이 크다).

콘솔 메뉴 이름은 바뀔 수 있으니 비슷한 항목을 찾으면 된다.

## 1. Object Storage 버킷

1. 콘솔 → **Object Storage** → 이용 신청 (처음 한 번)
2. **버킷 생성**: 이름 `science26-backup` (전 세계에서 유일해야 해서 겹치면 뒤에 숫자 추가)
3. 공개 설정은 **비공개** 그대로

## 2. 백업 전용 인증키 (권장: 서브 계정)

메인 계정 키를 쓰면 키가 새어 나갔을 때 서버·결제까지 위험하다. Object Storage 만 쓸 수 있는 서브 계정을 만든다.

1. 콘솔 → **Sub Account** → 서브 계정 생성: `science26-backup`, 접근 유형 **API Gateway 접근** 체크
2. 정책: **NCP_OBJECT_STORAGE_MANAGER** (Object Storage 만)
3. 그 서브 계정의 **Access Key** 생성 → Access Key ID 와 Secret Key 복사

## 3. 서버 설정

```bash
sudo nano /etc/science26-backup.env
```

```
AWS_ACCESS_KEY_ID=(Access Key ID)
AWS_SECRET_ACCESS_KEY=(Secret Key)
BACKUP_BUCKET=science26-backup
BACKUP_KEEP_DAYS=7
```

```bash
sudo chmod 600 /etc/science26-backup.env
sudo bash /opt/science26/scripts/backup.sh
```

마지막에 `백업 완료` 가 나오면 성공. cron 은 `server-setup.sh` 가 이미 등록해 두었다 (`/etc/cron.d/science26-backup`).
로그: `/var/log/science26-backup.log`

## 4. 복구

```bash
sudo bash /opt/science26/scripts/restore.sh                         # 백업 목록
sudo bash /opt/science26/scripts/restore.sh science26-20261201-0400.sql.gz
```

`복구` 를 입력해야 진행된다. 현재 DB 폴더는 지우지 않고 `/data/postgres.before-restore-<시각>` 으로 옮겨 둔다.
복구 후 대시보드 로그인·학생 페이지를 확인하고, 문제 없으면 옮겨 둔 폴더를 지운다.

## 비용

백업 하나는 학생 DB 크기에 따라 수 MB~수백 MB. 7일치만 남기므로 Object Storage 요금은 아주 작다.
