"""학생 compose를 플랫폼 규칙대로 다시 쓴다 (명세 8장 deploying 단계).

원본은 그대로 실행하지 않는다. 허용 키만 옮기고 라벨·네트워크·리소스 한도·환경변수를 강제로 넣는다.
"""

from pathlib import Path

from app.services.validation import ComposeSpec, _labels

# 학생이 붙인 traefik 라벨은 모두 버리고 플랫폼이 만든 것만 쓴다.
_KEEP_KEYS = ("command", "expose", "depends_on", "healthcheck")


def _walk(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {_walk(k, fn): _walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    return obj


def _student_literal(obj):
    """학생 compose 의 문자열을 compose 규칙대로 해석한 '실제 값'으로 바꾼다 ($$ → $).

    ${VAR} 치환은 지원하지 않고 글자 그대로 둔다. 치환을 허용하면 워커 환경의 비밀값이 새어 나갈 수 있다.
    """
    return _walk(obj, lambda s: s.replace("$$", "$"))


def escape_interpolation(spec: dict) -> dict:
    """compose 파일에 쓰기 직전에 모든 $ 를 $$ 로 바꿔 docker compose 가 변수 치환을 하지 않게 한다."""
    return _walk(spec, lambda s: s.replace("$", "$$"))

FRONT_PRIORITY_BASE = 1_000
API_PRIORITY_BASE = 1_000_000


def project_name(student_no: str, version: int) -> str:
    return f"stu-{student_no}-v{version}"


def network_name(student_no: str) -> str:
    return f"stu-{student_no}-net"


def image_name(student_no: str, service: str, version: int) -> str:
    return f"s26/stu-{student_no}-{service}:v{version}"


def traefik_labels(
    student_no: str, slug: str, version: int, seq: int, public_host: str, edge_network: str,
    port: int, *, api: bool = False,
) -> dict[str, str]:
    """버전별 라우터. 엔트리포인트를 지정하지 않아 web·websecure·internal 모두에 붙는다
    (TLS는 websecure 엔트리포인트 기본값으로 적용).

    seq(배포할 때마다 증가)가 클수록 우선이라 새로 띄운 스택이 기동 즉시 트래픽을 받고,
    실패하면 그 스택만 내려서 이전 스택으로 돌아간다. 롤백으로 옛 버전을 띄울 때도 seq 는 새 값이다.

    라우터 이름은 학번 기준, 경로는 학생이 정한 링크 이름(slug) 기준.
    """
    base = f"/students/{slug}"
    name = f"stu-{student_no}-v{version}" + ("-api" if api else "")
    prefix = f"{base}/api" if api else base
    labels = {
        "traefik.enable": "true",
        "traefik.docker.network": edge_network,
        f"traefik.http.routers.{name}.rule": f"Host(`{public_host}`) && PathPrefix(`{prefix}`)",
        f"traefik.http.routers.{name}.priority": str(
            (API_PRIORITY_BASE if api else FRONT_PRIORITY_BASE) + seq
        ),
        f"traefik.http.routers.{name}.service": name,
        f"traefik.http.services.{name}.loadbalancer.server.port": str(port),
        f"traefik.http.middlewares.{name}-strip.stripprefix.prefixes": prefix,
    }
    middlewares = [f"{name}-strip"]
    if not api:
        # /students/1411 → /students/1411/ (상대경로 에셋이 깨지지 않게)
        labels[f"traefik.http.middlewares.{name}-slash.redirectregex.regex"] = f"^(https?://[^/]+{base})$"
        labels[f"traefik.http.middlewares.{name}-slash.redirectregex.replacement"] = "${1}/"
        labels[f"traefik.http.middlewares.{name}-slash.redirectregex.permanent"] = "true"
        middlewares.insert(0, f"{name}-slash")
    labels[f"traefik.http.routers.{name}.middlewares"] = ",".join(middlewares)
    return labels


def hardening(memory_mb: int, cpus: float, pids: int) -> dict:
    return {
        "mem_limit": f"{memory_mb}m",
        "memswap_limit": f"{memory_mb}m",
        "cpus": cpus,
        "pids_limit": pids,
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "read_only": True,
        "tmpfs": ["/tmp:size=64m"],
        "restart": "on-failure:3",
    }


def _env_list(env) -> dict[str, str]:
    if not env:
        return {}
    if isinstance(env, list):
        out = {}
        for item in env:
            k, _, v = str(item).partition("=")
            out[k] = v
        return out
    return {str(k): "" if v is None else str(v) for k, v in env.items()}


def rewrite(
    spec: ComposeSpec,
    *,
    root: Path,
    student_no: str,
    slug: str,
    version: int,
    seq: int,
    env: dict[str, str],
    public_host: str,
    edge_network: str,
    memory_mb: int,
    stack_memory_mb: int,
    cpus: float,
    pids: int,
) -> dict:
    per_service_mb = min(memory_mb, stack_memory_mb // len(spec.services))
    services = {}
    for name, svc in spec.services.items():
        svc = _student_literal(svc)
        out: dict = {k: svc[k] for k in _KEEP_KEYS if k in svc}

        if "build" in svc:
            build = svc["build"] if isinstance(svc["build"], dict) else {"context": svc["build"]}
            out["build"] = {
                **build,
                "context": str((root / str(build.get("context", "."))).resolve()),
            }
            out["image"] = image_name(student_no, name, version)
        else:
            out["image"] = svc["image"]

        if "env_file" in svc:
            files = svc["env_file"] if isinstance(svc["env_file"], list) else [svc["env_file"]]
            out["env_file"] = [
                str((root / (f if isinstance(f, str) else f["path"])).resolve()) for f in files
            ]
        out["environment"] = {**_env_list(svc.get("environment")), **env}

        labels = {k: v for k, v in _labels(svc).items() if not k.startswith("traefik.")}
        labels["science26.student"] = student_no
        labels["science26.version"] = str(version)
        networks = ["default"]
        if name == spec.public:
            labels.update(traefik_labels(student_no, slug, version, seq, public_host, edge_network, spec.ports[name]))
            networks.append("edge")
        if name == spec.api:
            labels.update(traefik_labels(student_no, slug, version, seq, public_host, edge_network, spec.ports[name], api=True))
            if "edge" not in networks:
                networks.append("edge")
        out["labels"] = labels
        out["networks"] = networks
        out.update(hardening(per_service_mb, cpus, pids))
        services[name] = out

    return {
        "name": project_name(student_no, version),
        "services": services,
        "networks": {
            # 학생 스택 내부 전용. 워커가 미리 만들고 postgres·redis 컨테이너를 붙인다.
            "default": {"name": network_name(student_no), "external": True},
            "edge": {"name": edge_network, "external": True},
        },
    }


STATIC_NGINX_CONF = """\
server {
    listen 8080;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location ~* \\.apk$ {
        types { application/vnd.android.package-archive apk; }
        add_header Content-Disposition "attachment";
    }
}
"""

STATIC_DOCKERFILE = """\
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/
"""


def static_compose(
    *, student_no: str, slug: str, version: int, seq: int, context: Path, public_host: str, edge_network: str,
    memory_mb: int, cpus: float, pids: int,
) -> dict:
    """정적·앱 타입: nginx 이미지 1개짜리 스택."""
    svc = {
        "build": {"context": str(context)},
        "image": image_name(student_no, "web", version),
        "labels": {
            "science26.student": student_no,
            "science26.version": str(version),
            **traefik_labels(student_no, slug, version, seq, public_host, edge_network, 8080),
        },
        "networks": ["edge"],
        **hardening(min(memory_mb, 128), cpus, pids),
    }
    svc["tmpfs"] = ["/tmp:size=64m", "/var/cache/nginx:size=16m", "/var/run:size=1m"]
    return {
        "name": project_name(student_no, version),
        "services": {"web": svc},
        "networks": {"edge": {"name": edge_network, "external": True}},
    }
