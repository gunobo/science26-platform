# science26-platform

학생이 과학 프로젝트 결과물을 올리면 `science26.bssm.dev/students/{링크이름}/` 에 자동 배포되는 플랫폼.
정적 웹, 풀스택(docker compose), 안드로이드 앱(APK 소개 페이지) 세 종류를 받는다.

## 구성

| 서비스 | 기술 | 역할 |
|---|---|---|
| `web` | React Native (TS) + Expo Web → nginx | 대시보드(`upload.` 호스트)·공개 목록(루트 호스트) |
| `api` | FastAPI, SQLAlchemy 2, Alembic | 인증, 업로드·검증, 프로젝트·관리자 API |
| `worker` | 같은 코드 + arq | 빌드·배포·롤백·슬립·모니터링 |
| `postgres` / `redis` | PostgreSQL 16 / Redis 7 | 플랫폼 메타데이터, 세션·큐 + 학생별 DB·ACL 계정 |
| `traefik` | Traefik v3 | Docker 라벨 라우팅, 슬립·미배포 폴백 |
| `docker-proxy` | docker-socket-proxy | 워커·Traefik만 Docker API 접근 (API 컨테이너엔 소켓 없음) |
| `cloudflared` | Cloudflare Tunnel | 외부 HTTPS 인입 (`--profile tunnel`) |

```
api/          FastAPI 앱, 워커, Alembic 마이그레이션, 테스트
web/          Expo 대시보드·공개 목록
infra/        Traefik 폴백 라우터, Redis ACL 엔트리포인트, Postgres 초기 SQL
scripts/      비밀값 생성, 백업(pg_dump → NCP Object Storage), 방화벽
```

## 실행

```bash
cp .env.example .env
./scripts/gen-secrets.sh >> .env   # 생성된 값으로 빈 칸 채우기
docker compose up -d --build                    # 로컬
docker compose --profile tunnel up -d --build   # 운영 (Cloudflare Tunnel)
```

- 구글 OAuth 리디렉트 URI: `https://{UPLOAD_HOST}/api/v1/auth/google/callback`
- 관리자: `.env` 의 `ADMIN_EMAILS`. 학생은 관리자 화면에서 `email,학번,이름` CSV를 올려야 업로드 가능
- 로컬 개발 로그인: api 에 `DEV_LOGIN=true` 를 주고 `localhost` 에서 접속하면 이메일만으로 로그인 (운영에서는 켜지 말 것)
- 운영 서버 부팅 시 `scripts/firewall.sh` 로 학생 컨테이너의 내부 대역 접근 차단, cron 으로 `scripts/backup.sh` 일 1회

## 배포 흐름

1. 대시보드에서 타입 선택 후 zip / index.html / GitHub 저장소 / APK 제출
2. API가 규격 검사(zip 슬립·심볼릭 링크·용량·compose 금지 키·절대경로 경고)를 바로 하고 실패 시 즉시 오류 반환
3. 통과하면 릴리스 생성, `lock:project:{학번}` 획득, arq 큐 등록
4. 워커: `validating → building → deploying → active`. 빌드 로그는 SSE로 실시간 표시
5. 새 스택(`stu-{학번}-v{버전}`)을 띄우고 Traefik 경유 헬스체크 통과 시 이전 스택 제거. 실패하면 새 스택만 내리고 이전 버전이 계속 서빙

## 학생 풀스택 compose 규칙

- 루트에 `docker-compose.yml`, 서비스 최대 3개
- 공개 서비스에 `science26.public=true` (→ `/students/{링크이름}/`), API 서비스는 `science26.api=true` (→ `/students/{링크이름}/api/`, prefix 제거 후 전달)
- 포트: `science26.port` 라벨 → 없으면 `expose` 첫 값 → 없으면 80
- 허용 키: `build, image, environment, env_file, command, expose, depends_on, healthcheck, labels`
- 금지: `ports, volumes, privileged, cap_add, network_mode, pid, devices, deploy`, DB·Redis 이미지, Docker Hub 공식 이미지 외 `image`
- 자동 주입: `DATABASE_URL`, `REDIS_URL`, `REDIS_KEY_PREFIX`, `BASE_PATH`, `PUBLIC_URL` + 학생이 대시보드에서 설정한 환경변수
- 강제 적용: 메모리 256MB(스택 합계 512MB), CPU 0.5, PIDs 128, `cap_drop: ALL`, `no-new-privileges`, `read_only` + `/tmp` tmpfs 64MB, `restart: on-failure:3`

## 명세서와 다른 점

- **링크 이름(slug)**: 학번 대신 학생이 정한 이름으로 링크가 열린다 (`/students/space-runner/`). 기본값은 학번, 바꾸면 자동 재배포, 학번 주소로 들어오면 새 주소로 리다이렉트. 컨테이너·DB 계정 등 내부 식별자는 계속 학번
- **학생 DB 네트워크**: 공용 `data-net` 대신 학생별 `stu-{학번}-net` 에 postgres·redis 컨테이너를 별칭으로 붙인다. 학생 백엔드끼리 같은 네트워크를 공유하지 않게 하기 위함
- **설정 테이블**: 업로드 마감·리소스 한도 저장용 `platform_settings` 테이블 추가 (명세의 5개 테이블 외)
- **릴리스 타입**: `releases.type` 컬럼 추가 (릴리스마다 타입이 바뀔 수 있어서)
- **라우터 우선순위**: 배포마다 증가하는 순번을 Traefik 우선순위로 써서, 롤백으로 옛 버전을 띄워도 새로 띄운 스택이 트래픽을 받는다
- **APK 서명 검사**: v1(META-INF 서명 파일) 또는 v2+(APK Signing Block) 존재 여부만 확인. 서명의 암호학적 유효성까지는 검증하지 않음
- **BuildKit 캐시**: 학생별 분리는 아직 안 함 (기본 빌더 캐시 공유)

## 개발

```bash
cd api && uv venv --python 3.12 && uv pip install -e ".[dev]" && .venv/bin/pytest
cd web && npm install && npx tsc --noEmit && npx expo export -p web
```

## 라이선스

MIT
