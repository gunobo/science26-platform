# NCP 서버 만들기

크레딧(10만)으로 올해 말까지 운영하는 기준. 콘솔 메뉴 이름은 바뀔 수 있으니 비슷한 항목을 찾으면 된다.

## 1. 네트워크 (VPC 환경)

1. **VPC** 생성: 예) `science26-vpc`, `10.0.0.0/16`
2. **Subnet** 생성: `10.0.1.0/24`, **Public**, 용도 일반
3. **ACG**(방화벽) 생성 후 인바운드 규칙
   | 프로토콜 | 접근 소스 | 포트 | 용도 |
   |---|---|---|---|
   | TCP | 내 IP/32 | 22 | SSH (학교·집 IP만) |
   | TCP | 0.0.0.0/0 | 80 | Let's Encrypt 인증·HTTPS 리다이렉트 |
   | TCP | 0.0.0.0/0 | 443 | 서비스 |

   아웃바운드는 전체 허용(기본값) 그대로 둔다. 학생 앱의 외부 API 호출과 이미지 다운로드에 필요하다.

## 2. 서버

- 이미지: **Ubuntu 22.04** (또는 24.04)
- 타입: **Standard** 계열 **2vCPU · 8GB** 로 시작. 평가·발표 날만 상위 사양으로 올렸다가 내린다 (시간 단위 과금)
- 스토리지: 기본 디스크 그대로
- 위 VPC·Subnet·ACG 선택, 인증키(.pem) 새로 만들어 보관
- **공인 IP** 할당 → 서버에 연결

## 3. 추가 스토리지

- **Block Storage 100GB** 생성 → 서버에 연결. 업로드 원본, 학생 이미지, DB 데이터가 여기 들어간다
- 서버에서 `lsblk` 로 장치 이름 확인 (보통 `/dev/xvdb`)

## 4. 서버 세팅

```bash
ssh -i science26.pem root@<공인IP>
curl -fsSL https://raw.githubusercontent.com/gunobo/science26-platform/main/scripts/server-setup.sh -o setup.sh
less setup.sh                # 내용 확인
bash setup.sh /dev/xvdb
```

Docker 설치, `/data` 마운트, 스왑 4GB, 저장소 클론(`/opt/science26`), 방화벽·백업 등록까지 한다.

## 5. DNS

bssm.dev DNS 관리 화면에서 A 레코드 두 개를 서버 공인 IP로:

- `science26.bssm.dev`
- `science26-upload.bssm.dev`

대시보드를 `upload.science26` 같은 두 단계가 아니라 `science26-upload` 한 단계로 둔 건 DNS 관리상 한 단계 서브도메인만 쓸 수 있어서다.
Cloudflare 에서 DNS 를 관리한다면 두 레코드 모두 **DNS only(회색 구름)** 로 둔다. 프록시를 켜면 Let's Encrypt HTTP 인증과 충돌할 수 있다.

## 6. 환경변수와 실행

```bash
cd /opt/science26
cp .env.example .env
./scripts/gen-secrets.sh     # 출력값을 .env 에 붙여넣기
vi .env                      # 도메인, 구글 OAuth, ADMIN_EMAILS, ACME_EMAIL, DATA_ROOT=/data
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

- 구글 OAuth 리디렉트 URI: `https://science26-upload.bssm.dev/api/v1/auth/google/callback`
- 작은 서버에서는 `.env` 에 `CONCURRENT_BUILDS=1`, `RELEASES_KEPT=2` 추가 권장
- 첫 접속 시 인증서 발급에 수십 초 걸릴 수 있다

## 7. 백업 (선택)

Object Storage 버킷과 API 인증키를 만든 뒤 `/etc/science26-backup.env`:

```
NCP_ACCESS_KEY=...
NCP_SECRET_KEY=...
BACKUP_BUCKET=science26-backup
```

매일 04:00 에 `pg_dumpall` 결과를 올리고 7일 지난 것은 지운다.

## 업데이트

```bash
cd /opt/science26 && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
