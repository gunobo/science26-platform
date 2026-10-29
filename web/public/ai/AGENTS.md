# science26 배포 가이드 (AI 코딩 도구용)

이 프로젝트는 학교 배포 플랫폼 **science26** 에 올릴 학생 과제야.
너(AI)의 일은 이 프로젝트를 아래 규칙에 맞게 고쳐서, 학생이 대시보드에 **올리기만 하면 바로 배포되는 상태**로 만드는 거야.
코드를 고치기 전에 어떤 타입(정적 웹 / 풀스택 / 안드로이드 앱)인지 먼저 판단하고, 끝나면 마지막의 "끝낼 때 학생에게 알려줄 것"을 지켜.

- 배포 주소: `https://science26.bssm.dev/students/{링크이름}/` (링크이름은 학생이 대시보드에서 정함, 기본값은 학번)
- 업로드: `https://science26-upload.bssm.dev` (학생이 직접 올림. 너는 업로드할 파일을 준비만 해)
- 링크이름은 나중에 바뀔 수 있어. 가능하면 경로를 하드코딩하지 말고 상대경로나 `BASE_PATH` 환경변수를 써.

---

## 1. 타입 고르기

| 프로젝트 | 타입 | 올리는 것 |
|---|---|---|
| HTML/CSS/JS, React·Vue·Svelte(Vite), Expo Web 등 서버 없이 돌아가는 것 | **정적 웹** | 빌드 결과 폴더를 zip (또는 index.html 하나) |
| 백엔드(Node, Python, Java 등)나 DB가 필요한 웹 | **풀스택** | 프로젝트 전체 zip 또는 GitHub 공개 저장소 |
| 안드로이드 앱 | **앱** | 서명된 APK + 스크린샷 1~5장 |

백엔드 없이 되는 건 정적 웹으로 가는 게 제일 안정적이야. 서버가 꼭 필요할 때만 풀스택을 골라.

---

## 2. 정적 웹

페이지는 `/students/{링크이름}/` 아래에서 열리고, 서버는 그 접두사를 떼고 zip 루트의 파일을 그대로 보여줘.
그래서 **`/` 로 시작하는 절대경로(`/assets/app.js`, `/logo.png`)는 깨져.** 업로드 화면에서도 경고가 떠.

### 해야 할 것
- 에셋 경로를 상대경로로 바꾸기
  - Vite: `vite.config` 에 `base: './'`
  - Create React App: `package.json` 에 `"homepage": "."`
  - Expo Web: `app.json` 의 `expo.experiments.baseUrl` 을 `"/students/{링크이름}"` 으로 하고 `npx expo export -p web`
  - Next.js: `output: 'export'`, `basePath: '/students/{링크이름}'`, `images.unoptimized: true` 후 `out/` 폴더 사용
  - 순수 HTML: `src="/a.js"` → `src="./a.js"` 또는 `src="a.js"`
- 클라이언트 라우터
  - 가장 쉬운 방법은 해시 라우터(`HashRouter`, `createWebHashHistory`)
  - 일반 라우터를 쓰려면 basename 을 현재 경로에서 계산: `window.location.pathname.match(/^\/students\/[^/]+/)?.[0] ?? '/'`
  - 없는 경로는 서버가 `index.html` 을 돌려줘서 새로고침해도 괜찮아
- 빌드 후 결과 폴더(`dist/`, `build/`, `out/`)를 zip 으로 묶기. `index.html` 이 zip 루트나 최상위 폴더 하나 안에 있어야 해

### 제한
- zip 100MB 이하, 풀었을 때 1GB 이하, 심볼릭 링크 금지
- `fetch('/api/...')` 처럼 다른 서버를 부르려면 그 서버 주소를 절대 URL 로 써야 해 (정적 웹엔 백엔드가 없어)

---

## 3. 풀스택 (docker compose)

플랫폼이 학생의 `docker-compose.yml` 을 검사한 뒤 보안 설정을 덧붙여 다시 써서 실행해.
**규칙을 어기면 업로드 단계에서 바로 거부돼.**

### docker-compose.yml 규칙
- 프로젝트 **루트**에 `docker-compose.yml` (또는 최상위 폴더 하나 안)
- 최상위 키는 `services` 만 (`version`, `name` 은 무시됨). `volumes:`, `networks:` 최상위 키 금지
- 서비스 최대 **3개**
- 서비스에 쓸 수 있는 키: `build`, `image`, `environment`, `env_file`, `command`, `expose`, `depends_on`, `healthcheck`, `labels`
- **금지 키**: `ports`, `volumes`, `privileged`, `cap_add`, `network_mode`, `pid`, `devices`, `deploy`, `restart` 등 위 목록에 없는 모든 키
- `image` 는 Docker Hub **공식 이미지만** (`node:20-alpine` 가능, `someone/app` 불가). 직접 만들 거면 `build` 사용
- `build.context`, `dockerfile`, `env_file` 은 프로젝트 폴더 안이어야 해 (`../` 금지)
- **DB·Redis 서비스를 넣지 마** (`postgres`, `mysql`, `mariadb`, `redis`, `mongo` 이미지 금지). 플랫폼이 자동으로 넣어주는 걸 써
- compose 의 `${VAR}` 변수 치환은 **동작하지 않아** (글자 그대로 들어가). 값은 `environment` 에 직접 쓰거나 대시보드 환경변수로 넣고, 앱 코드에서 환경변수로 읽어. 쉘 변수는 `command: ["sh", "-c", "echo $$HOME"]` 처럼 `$$` 로 써

### 라벨 (중요)
- 브라우저가 여는 서비스에 `science26.public=true` → `https://science26.bssm.dev/students/{링크이름}/`
- 프론트와 API 서버를 나눴다면 API 서비스에 `science26.api=true` → `/students/{링크이름}/api/`
- 두 경우 모두 **접두사를 떼고** 전달돼. 즉 서버는 `/` 와 `/items` 처럼 루트 기준 경로로 받아
  - 공개 서비스로 `/students/x/about` 요청 → 컨테이너는 `/about` 을 받음
  - API 서비스로 `/students/x/api/items` 요청 → 컨테이너는 `/items` 를 받음
- 서비스가 1개뿐이면 `science26.public` 라벨은 생략 가능
- 포트: `science26.port=3000` 라벨 → 없으면 `expose` 의 첫 값 → 없으면 80. 1024 이상 포트(3000, 8000 등)를 써

### 자동으로 들어가는 환경변수
| 변수 | 예시 | 용도 |
|---|---|---|
| `DATABASE_URL` | `postgresql://stu_1411:...@postgres:5432/stu_1411` | 학생 전용 PostgreSQL DB |
| `REDIS_URL` | `redis://stu_1411:...@redis:6379/0` | 학생 전용 Redis 계정 |
| `REDIS_KEY_PREFIX` | `stu_1411:` | **모든 Redis 키 앞에 반드시 붙여야 함** |
| `BASE_PATH` | `/students/space-runner` | 페이지가 열리는 경로 |
| `PUBLIC_URL` | `https://science26.bssm.dev/students/space-runner` | 외부에서 보이는 전체 주소 |

학생이 대시보드에서 추가한 환경변수(API 키 등)도 같이 들어가. 비밀값을 코드나 저장소에 넣지 말고 환경변수로 읽어.

- `DATABASE_URL` 은 `postgresql://` 형식이야. SQLAlchemy async 는 `postgresql+asyncpg://` 로 바꿔서 쓰고, Prisma·node-postgres·psycopg 는 그대로 쓰면 돼
- 테이블은 앱이 시작할 때 만들거나 마이그레이션을 돌려. DB 는 처음엔 비어 있어
- Redis 에서 `KEYS`, `SCAN`, `FLUSHALL`, `FLUSHDB`, `CONFIG`, `SELECT` 는 막혀 있어. 키는 항상 `REDIS_KEY_PREFIX` 로 시작해야 하고, 0번 DB 만 써
- Redis 는 모든 학생이 512MB 를 나눠 쓰는 **캐시**야. 사라지면 안 되는 데이터는 PostgreSQL 에 저장하고, Redis 키에는 TTL 을 걸어
- PostgreSQL 은 학생당 1GB 를 넘으면 접속이 막혀. 파일·이미지 같은 큰 데이터를 DB 에 넣지 마

### 실행 환경 (지켜야 동작함)
- 파일시스템이 **읽기 전용**이야. 쓰기 가능한 곳은 `/tmp` (64MB, 재시작하면 사라짐) 뿐
  - SQLite, 업로드 파일 저장, 로그 파일 쓰기 금지. 데이터는 `DATABASE_URL` 로, 로그는 stdout 으로
  - `npm start` 대신 `CMD ["node", "server.js"]` 처럼 직접 실행 (npm 이 캐시·로그 파일을 쓰려다 실패할 수 있어)
  - Python 은 `ENV PYTHONDONTWRITEBYTECODE=1`
- 메모리: 서비스당 256MB, 스택 합계 512MB. CPU 0.5개
- 개발 서버(`vite dev`, `next dev`, `nodemon`, `flask run --debug`) 말고 프로덕션 빌드·서버로 실행
- 빌드 10분 제한, 이미지 합계 2GB, 소스 200MB
- `0.0.0.0` 에 바인딩 (localhost 만 열면 접속 안 됨)
- 컨테이너는 최소 권한으로 돌아. 허용되는 건 `CHOWN`, `SETUID`, `SETGID`, `NET_BIND_SERVICE` 뿐이라 `nginx:alpine`·`httpd` 같은 공식 이미지는 그대로 동작해. 그 밖의 권한이 필요한 프로그램은 안 돼
- 쓸 수 있는 임시 폴더: `/tmp`(64MB), `/run`, `/var/cache/nginx`. 그 외 경로에 파일을 쓰면 실패해
- 컨테이너 로그는 5MB 씩 2개까지만 남아. 로그를 너무 많이 찍지 마
- 30분 동안 방문이 없으면 잠들었다가 첫 방문 때 다시 켜져. 시작이 빠를수록 좋아
- 배포 확인: 플랫폼이 공개 서비스의 `/` 에 GET 을 보내서 **60초 안에 2xx 또는 3xx** 가 와야 성공

### 프론트에서 API 부르기
- 같은 스택의 API 는 **상대경로**로: `fetch('api/items')` (앞에 `/` 없이). 페이지가 `/students/x/` 에 있으니 `/students/x/api/items` 로 가
- 서비스 1개가 화면과 API 를 다 처리하면 `fetch('items')` 처럼 그 서버 기준 상대경로를 써
- 백엔드끼리는 서비스 이름으로: `http://api:8000`

### 예시
```yaml
services:
  web:
    build: ./frontend          # 빌드한 정적 파일을 nginx(8080) 등으로 서빙
    expose: ["8080"]
    labels:
      science26.public: "true"
  api:
    build: ./backend
    command: ["node", "server.js"]
    expose: ["3000"]
    labels:
      science26.api: "true"
```

### 로컬에서 확인하기
- 로컬에서 포트를 열어 보고 싶으면 `docker-compose.override.yml` 에 `ports` 를 넣어 (플랫폼은 이 파일을 쓰지 않아)
- 로컬 DB 가 필요하면 override 파일에 postgres 서비스를 넣고 `DATABASE_URL` 을 맞춰
- `docker compose up --build` 로 실제로 뜨는지 확인

---

## 4. 모바일 앱
대시보드의 **모바일 앱** 타입은 아래 셋 중 **하나 이상**과 스크린샷 1~5장(png/jpg/webp, 각 5MB 이하), 앱 이름·설명을 받아서 설치 버튼·QR 코드가 있는 소개 페이지를 만들어.

| 항목 | 준비 방법 | 제한 |
|---|---|---|
| Android APK (선택) | **서명된 APK** (debug 서명도 가능). `./gradlew assembleRelease`, Expo 는 `eas build -p android --profile preview` | 150MB |
| iPhone TestFlight 링크 (선택) | 애플 개발자 계정으로 TestFlight 공개 링크 발급: `https://testflight.apple.com/join/...` | 링크만 |
| 시연 영상 (선택) | 실행 화면 녹화 | mp4·webm·mov, 100MB |

- iPhone 은 설치 파일을 직접 받을 수 없어. 애플 개발자 계정이 없으면 **시연 영상**을 쓰거나, React Native(Expo)·Flutter 처럼 웹으로도 빌드되는 앱이면 **웹 빌드를 정적 웹으로** 올리는 걸 같이 안내해 (`npx expo export -p web`, `flutter build web --base-href ./`)
- 영상은 너무 크면 해상도를 낮춰 (예: `ffmpeg -i in.mov -vf scale=-2:720 -c:v libx264 -crf 28 -c:a aac out.mp4`)

---

## 5. 주의
- 모든 학생 페이지는 `science26.bssm.dev` 라는 같은 도메인을 써. **localStorage·쿠키는 다른 학생 페이지와 공유되니까** 비밀번호·토큰 같은 민감한 값을 저장하지 마. 게임 점수·설정처럼 노출돼도 괜찮은 값만 저장하고, 키 이름에 프로젝트 이름을 붙여 다른 학생과 겹치지 않게 해
- 학생이 작성한 코드의 의도를 바꾸지 마. 배포에 필요한 부분만 고쳐

---

## 끝낼 때 학생에게 알려줄 것
1. 고른 타입 (정적 웹 / 풀스택 / 앱)
2. 바꾼 파일과 이유를 짧게
3. 올릴 것: 만든 zip 파일 경로, 또는 GitHub 저장소 주소와 브랜치
4. 대시보드에서 추가해야 할 환경변수 이름 (값은 학생이 직접 입력)
5. 업로드: `https://science26-upload.bssm.dev` → 타입 선택 → 파일 또는 저장소 주소 → "올리고 배포하기"

## science26 MCP 가 연결돼 있으면
`science26` MCP 도구가 보이면 학생 대신 직접 배포해도 돼 (학생이 배포해 달라고 했을 때만).
1. `project_status` 로 지금 상태와 링크 이름 확인
2. 빌드해서 zip 을 만든 뒤 `create_upload` (type: static 또는 fullstack) → 돌려받은 `curl` 명령으로 올리기. 공개 GitHub 저장소면 `deploy_github`
3. `release_status` 로 결과 확인. 실패하면 `log_tail` 을 읽고 고쳐서 다시 올리기 (10분에 5번까지라 무작정 반복하지 마)
4. 끝나면 학생에게 주소와 바꾼 내용을 알려 줘
- 처음 연결하면 `.gitignore` 에 `.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `.env`, `.env.*` 가 있는지 보고 없으면 추가해
- 토큰(`s26_…`)이나 업로드 주소를 코드·커밋·zip·로그에 남기지 마. 커밋·zip 전에 `s26_` 가 들어간 파일이 없는지 확인해
- 서버는 올린 파일에서 살아 있는 토큰을 발견하면 배포를 멈추고 그 토큰을 바로 폐기해. 그러면 학생이 대시보드에서 새로 만들어야 해
