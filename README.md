# science26-platform

학생이 과학 프로젝트 결과물을 올리면 `science26.bssm.dev/students/{링크이름}/` 에 자동 배포되는 플랫폼.
정적 웹, 풀스택(docker compose), 모바일 앱(APK·TestFlight 링크·시연 영상 소개 페이지) 세 종류를 받는다.

## 구성

| 서비스 | 기술 | 역할 |
|---|---|---|
| `web` | React Native (TS) + Expo Web → nginx | 대시보드(`upload.` 호스트)·공개 목록(루트 호스트) |
| `api` | FastAPI, SQLAlchemy 2, Alembic | 인증, 업로드·검증, 프로젝트·관리자 API |
| `worker` | 같은 코드 + arq | 빌드·배포·롤백·슬립·모니터링 |
| `postgres` / `redis` | PostgreSQL 16 / Redis 7 | 플랫폼 메타데이터, 세션·큐 + 학생별 DB·ACL 계정 |
| `traefik` | Traefik v3 | Docker 라벨 라우팅, Let's Encrypt HTTPS, 슬립·미배포 폴백 |
| `docker-proxy` | docker-socket-proxy | 워커·Traefik만 Docker API 접근 (API 컨테이너엔 소켓 없음) |

```
api/          FastAPI 앱, 워커, Alembic 마이그레이션, 테스트
web/          Expo 대시보드·공개 목록
infra/        Traefik 폴백 라우터, Redis ACL 엔트리포인트, Postgres 초기 SQL
scripts/      비밀값 생성, 백업(pg_dump → NCP Object Storage), 방화벽
```

## 실행

```bash
# 로컬: http://science26-upload.localhost:8080 (대시보드), http://science26.localhost:8080 (공개 목록)
./scripts/setup-local.sh
docker compose up -d --build

# 운영 (NCP 공인 IP + Let's Encrypt): docs/ncp-setup.md 참고
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

- 구글 OAuth 리디렉트 URI: `https://{UPLOAD_HOST}/api/v1/auth/google/callback`
- 관리자: `.env` 의 `ADMIN_EMAILS`. 학생은 관리자 화면에서 `email,학번,이름` CSV를 올려야 업로드 가능
- 로컬 개발 로그인: api 에 `DEV_LOGIN=true` 를 주고 `localhost` 에서 접속하면 이메일만으로 로그인 (운영에서는 켜지 말 것)
- 운영 서버는 `scripts/server-setup.sh` 가 Docker 설치, `/data` 마운트, 방화벽(`scripts/firewall.sh`), 백업 cron(`scripts/backup.sh`, 설정·복구는 `docs/backup.md`)까지 세팅한다

## 배포 흐름

1. 대시보드에서 타입 선택 후 zip / index.html / GitHub 저장소 / APK 제출
2. API가 규격 검사(zip 슬립·심볼릭 링크·용량·compose 금지 키·절대경로 경고)를 바로 하고 실패 시 즉시 오류 반환
3. 통과하면 릴리스 생성, `lock:project:{학번}` 획득, arq 큐 등록
4. 워커: `validating → building → deploying → active`. 빌드 로그는 SSE로 실시간 표시
5. 새 스택(`stu-{학번}-v{버전}`)을 띄우고 Traefik 경유 헬스체크 통과 시 이전 스택 제거. 실패하면 새 스택만 내리고 이전 버전이 계속 서빙

## AI 코딩 도구로 배포 준비

`web/public/ai/AGENTS.md` (Codex) 와 `CLAUDE.md` (Claude Code) 가 `https://science26.bssm.dev/ai/` 에서 제공된다.
학생 대시보드의 "AI로 배포 준비하기" 카드에서 받는 명령과 학생 링크 이름이 들어간 프롬프트를 복사할 수 있다.
배포 규칙이 바뀌면 이 문서도 같이 고친다.

`examples/static-test/index.html` 은 정적 업로드 테스트용 단일 HTML 이다.

## 운영 서버 E2E 테스트

테스트 전용 계정(학번 9999)으로 실제 공개 주소에 정적 → 풀스택(`examples/fullstack-test`) → 중지·재시작 → 롤백 → 모바일 앱(TestFlight 링크·시연 영상, APK 는 있을 때만)까지 올려 보고, 끝나면 프로젝트와 계정을 지운다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm -v ./examples:/examples:ro worker python -m app.e2e
# APK 도 테스트: examples/app.apk 에 두고 --apk /examples/app.apk
```

## 학생 풀스택 compose 규칙

- 루트에 `docker-compose.yml`, 서비스 최대 3개
- 공개 서비스에 `science26.public=true` (→ `/students/{링크이름}/`), API 서비스는 `science26.api=true` (→ `/students/{링크이름}/api/`, prefix 제거 후 전달)
- 포트: `science26.port` 라벨 → 없으면 `expose` 첫 값 → 없으면 80
- 허용 키: `build, image, environment, env_file, command, expose, depends_on, healthcheck, labels`
- 금지: `ports, volumes, privileged, cap_add, network_mode, pid, devices, deploy`, DB·Redis 이미지, Docker Hub 공식 이미지 외 `image`
- 자동 주입: `DATABASE_URL`, `REDIS_URL`, `REDIS_KEY_PREFIX`, `BASE_PATH`, `PUBLIC_URL` + 학생이 대시보드에서 설정한 환경변수
- 강제 적용: 메모리 256MB(스택 합계 512MB), CPU 0.5, PIDs 128, `cap_drop: ALL`, `no-new-privileges`, `read_only` + `/tmp` tmpfs 64MB, `restart: on-failure:3`

## 명세서와 다른 점

- **학생 Redis 분리**: 명세의 공용 Redis 대신 학생 전용 인스턴스(`redis-students`, 512MB)를 둔다. 학생이 메모리를 채워도 세션·빌드 큐가 멈추지 않게
- **학생 DB 용량 차단**: 500MB 경고, 1GB 를 넘으면 접속 차단 (Postgres 에는 DB별 용량 제한이 없어서). 관리자가 정리해 한도 아래로 내려가면 자동 해제
- **네트워크**: 대시보드·API 는 `s26-front` 에만 있고, 학생 공개 서비스가 있는 `s26-edge` 에는 Traefik 만 붙는다

- **외부 인입**: Cloudflare Tunnel 대신 NCP 공인 IP + Traefik Let's Encrypt(HTTP-01). 헬스체크는 외부에 안 열린 `internal` 엔트리포인트(8000)로 한다

- **링크 이름(slug)**: 학번 대신 학생이 정한 이름으로 링크가 열린다 (`/students/space-runner/`). 기본값은 학번, 바꾸면 자동 재배포, 학번 주소로 들어오면 새 주소로 리다이렉트. 컨테이너·DB 계정 등 내부 식별자는 계속 학번
- **학생 DB 네트워크**: 공용 `data-net` 대신 학생별 `stu-{학번}-net` 에 postgres·redis 컨테이너를 별칭으로 붙인다. 학생 백엔드끼리 같은 네트워크를 공유하지 않게 하기 위함
- **설정 테이블**: 업로드 마감·리소스 한도 저장용 `platform_settings` 테이블 추가 (명세의 5개 테이블 외)
- **릴리스 타입**: `releases.type` 컬럼 추가 (릴리스마다 타입이 바뀔 수 있어서)
- **라우터 우선순위**: 배포마다 증가하는 순번을 Traefik 우선순위로 써서, 롤백으로 옛 버전을 띄워도 새로 띄운 스택이 트래픽을 받는다
- **APK 서명 검사**: v1(META-INF 서명 파일) 또는 v2+(APK Signing Block) 존재 여부만 확인. 서명의 암호학적 유효성까지는 검증하지 않음
- **BuildKit 캐시**: 학생별 분리는 아직 안 함 (기본 빌더 캐시 공유)

## 보안 메모

- 학생 페이지(`science26.bssm.dev`)와 대시보드(`science26-upload.bssm.dev`)는 출처는 다르지만 **같은 사이트**라 SameSite 쿠키가 실린다.
  그래서 API 는 상태를 바꾸는 요청에 `X-S26-Request` 헤더와 같은 출처(`Origin`, `Sec-Fetch-Site`)를 요구한다 (`api/app/middleware.py`)
- 업로드는 본문을 받기 전에 세션과 크기를 확인한다 (FastAPI 는 multipart 본문을 인증보다 먼저 읽는다)
- 대시보드·API 응답에는 `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, HSTS 를 붙인다
- `scripts/firewall.sh`: 컨테이너 → VPC 내부 대역 차단, 컨테이너 → 호스트 SSH 차단
- Traefik 은 읽기 전용 Docker 프록시(`docker-proxy-ro`)만 쓴다. 빌드·배포용 프록시(생성·exec 가능)는 워커만 접근
- 디스크 80% 에서 알림, 90% 에서 업로드 차단. 실패한 빌드의 파일·이미지는 바로 지운다
- 로그인·공개 엔드포인트는 IP 별 요청 제한 (한 반이 같은 IP 를 쓰므로 넉넉하게)
- 서버 점검(보안 업데이트, `.env` 보관, SSH 키 로그인): `docs/server-hardening.md`
- 학생 compose 의 `${...}` 치환은 막혀 있고, docker·git 은 비밀값이 없는 환경에서 실행한다
- 학생 라벨은 `science26.*` 만 허용, 학생 컨테이너 로그는 5MB × 2

## 개발

```bash
cd api && uv venv --python 3.12 && uv pip install -e ".[dev]" && .venv/bin/pytest
cd web && npm install && npx tsc --noEmit && npx expo export -p web
```

## 라이선스

MIT
