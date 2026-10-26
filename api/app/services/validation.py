"""업로드 규격 검사 (명세 5장). API(즉시 응답)와 워커(validating 단계)가 함께 쓴다."""

import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml


class ValidationError(Exception):
    def __init__(self, message: str, code: str = "UPLOAD_INVALID", detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


# ---- zip ----

def safe_extract(zip_path: Path, dest: Path, max_unpacked: int) -> None:
    """zip 슬립·심볼릭 링크·압축 폭탄을 거부하고 dest에 푼다."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValidationError("zip 파일을 열 수 없습니다")
    with zf:
        total = 0
        for info in zf.infolist():
            name = info.filename
            parts = PurePosixPath(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or re.match(r"^[A-Za-z]:", name):
                raise ValidationError(f"허용되지 않는 경로가 있습니다: {name}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValidationError(f"심볼릭 링크는 허용되지 않습니다: {name}")
            total += info.file_size
            if total > max_unpacked:
                raise ValidationError("압축 해제 후 용량이 1GB를 넘습니다")
        dest.mkdir(parents=True, exist_ok=True)
        dest_resolved = dest.resolve()
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ValidationError(f"허용되지 않는 경로가 있습니다: {info.filename}")
        zf.extractall(dest)


IGNORED_TOP = {"__MACOSX", ".DS_Store"}


def find_root(base: Path, marker: str) -> Path:
    """루트 또는 최상위 폴더 1개 안에서 marker 파일이 있는 폴더를 찾는다."""
    if (base / marker).is_file():
        return base
    entries = [p for p in base.iterdir() if p.name not in IGNORED_TOP]
    if len(entries) == 1 and entries[0].is_dir() and (entries[0] / marker).is_file():
        return entries[0]
    raise ValidationError(f"루트(또는 최상위 폴더 1개 안)에 {marker}이 없습니다")


# ---- 정적: 절대경로 검사 (F-13) ----

_ATTR_RE = re.compile(r"""\b(?:src|href)\s*=\s*["'](/[^"'/][^"']*|/)["']""", re.IGNORECASE)

ABSOLUTE_PATH_HINT = (
    "학생 페이지는 /students/{학번}/ 아래에서 열리므로 /로 시작하는 경로는 깨집니다. "
    "Vite는 base: './', Expo는 experiments.baseUrl 을 설정하세요."
)


def find_absolute_paths(html: str) -> list[str]:
    return sorted(set(m.group(1) for m in _ATTR_RE.finditer(html)))


def static_warnings(root: Path) -> list[dict]:
    html = (root / "index.html").read_text(errors="ignore")
    paths = find_absolute_paths(html)
    if not paths:
        return []
    return [{"code": "ABSOLUTE_PATH", "message": ABSOLUTE_PATH_HINT, "paths": paths[:20]}]


# ---- 풀스택: compose 정적 분석 ----

ALLOWED_SERVICE_KEYS = {
    "build", "image", "environment", "env_file", "command", "expose",
    "depends_on", "healthcheck", "labels",
}
FORBIDDEN_SERVICE_KEYS = {
    "ports", "volumes", "privileged", "cap_add", "network_mode", "pid", "devices", "deploy",
}
IGNORED_TOP_KEYS = {"version", "name"}
DB_IMAGES = ("postgres", "mysql", "mariadb", "redis", "mongo", "valkey", "keydb")
MAX_SERVICES = 3
PUBLIC_LABEL = "science26.public"
API_LABEL = "science26.api"
PORT_LABEL = "science26.port"


@dataclass
class ComposeSpec:
    services: dict
    public: str
    api: str | None = None
    ports: dict[str, int] = field(default_factory=dict)


def _labels(svc: dict) -> dict[str, str]:
    labels = svc.get("labels") or {}
    if isinstance(labels, list):
        out = {}
        for item in labels:
            k, _, v = str(item).partition("=")
            out[k] = v
        return out
    return {str(k): str(v) for k, v in labels.items()}


def _truthy(v: str | None) -> bool:
    return str(v).lower() in ("true", "1", "yes")


def _inside(root: Path, rel: str) -> bool:
    if rel.startswith("/"):
        return False
    return (root / rel).resolve().is_relative_to(root.resolve())


def _service_port(svc: dict, labels: dict[str, str]) -> int:
    if PORT_LABEL in labels:
        return int(labels[PORT_LABEL])
    expose = svc.get("expose") or []
    if expose:
        return int(str(expose[0]).split("/")[0])
    return 80


def forbidden(message: str, **detail) -> ValidationError:
    return ValidationError(message, code="COMPOSE_FORBIDDEN_KEY", detail=detail)


def parse_compose(text: str, root: Path) -> ComposeSpec:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValidationError(f"docker-compose.yml 을 읽을 수 없습니다: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ValidationError("docker-compose.yml 에 services 가 없습니다")

    extra_top = set(data) - {"services"} - IGNORED_TOP_KEYS
    if extra_top:
        raise forbidden(f"허용되지 않는 최상위 키: {', '.join(sorted(extra_top))}", keys=sorted(extra_top))

    services: dict = data["services"]
    if not services:
        raise ValidationError("서비스가 1개 이상 필요합니다")
    if len(services) > MAX_SERVICES:
        raise forbidden(f"서비스는 최대 {MAX_SERVICES}개입니다")

    public, api, ports = [], [], {}
    for name, svc in services.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", str(name)):
            raise ValidationError(f"서비스 이름은 영문 소문자·숫자·-·_ 만 쓸 수 있습니다: {name}")
        if not isinstance(svc, dict):
            raise ValidationError(f"{name}: 서비스 정의가 올바르지 않습니다")
        bad = set(svc) & FORBIDDEN_SERVICE_KEYS
        if bad:
            raise forbidden(f"{name}: 금지된 키 {', '.join(sorted(bad))}", service=name, keys=sorted(bad))
        unknown = set(svc) - ALLOWED_SERVICE_KEYS
        if unknown:
            raise forbidden(f"{name}: 허용되지 않는 키 {', '.join(sorted(unknown))}", service=name, keys=sorted(unknown))
        if "build" not in svc and "image" not in svc:
            raise ValidationError(f"{name}: build 또는 image 가 필요합니다")

        image = svc.get("image")
        if image and "build" not in svc:
            image = str(image)
            if "/" in image.split(":")[0] or "@" in image:
                raise forbidden(f"{name}: Docker Hub 공식 이미지만 쓸 수 있습니다 ({image})", service=name)
            if image.split(":")[0] in DB_IMAGES:
                raise forbidden(f"{name}: DB·Redis 서비스는 넣지 말고 주입되는 DATABASE_URL·REDIS_URL 을 쓰세요", service=name)

        build = svc.get("build")
        if build is not None:
            if isinstance(build, str):
                build = {"context": build}
            if not isinstance(build, dict) or set(build) - {"context", "dockerfile", "args", "target"}:
                raise forbidden(f"{name}: build 에는 context·dockerfile·args·target 만 쓸 수 있습니다", service=name)
            ctx = str(build.get("context", "."))
            if not _inside(root, ctx):
                raise forbidden(f"{name}: build context 는 프로젝트 폴더 안이어야 합니다", service=name)
            dockerfile = str(build.get("dockerfile", "Dockerfile"))
            if not _inside(root / ctx, dockerfile):
                raise forbidden(f"{name}: dockerfile 은 context 안이어야 합니다", service=name)
            if not (root / ctx / dockerfile).is_file():
                raise ValidationError(f"{name}: {ctx}/{dockerfile} 이 없습니다")

        env_files = svc.get("env_file") or []
        for ef in [env_files] if isinstance(env_files, str) else env_files:
            path = ef if isinstance(ef, str) else str(ef.get("path", ""))
            if not _inside(root, path):
                raise forbidden(f"{name}: env_file 은 프로젝트 폴더 안이어야 합니다", service=name)

        labels = _labels(svc)
        if _truthy(labels.get(PUBLIC_LABEL)):
            public.append(name)
        if _truthy(labels.get(API_LABEL)):
            api.append(name)
        try:
            ports[name] = _service_port(svc, labels)
        except ValueError:
            raise ValidationError(f"{name}: 포트 값이 올바르지 않습니다")

    if len(services) == 1 and not public:
        public = list(services)
    if len(public) != 1:
        raise ValidationError(f"공개 서비스 1개에 라벨 {PUBLIC_LABEL}=true 가 필요합니다")
    if len(api) > 1:
        raise ValidationError(f"{API_LABEL}=true 라벨은 1개 서비스에만 붙일 수 있습니다")
    return ComposeSpec(services=services, public=public[0], api=api[0] if api else None, ports=ports)


# ---- 앱(APK) ----

@dataclass
class ApkInfo:
    package: str
    version_name: str
    version_code: str


def inspect_apk(path: Path) -> ApkInfo:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValidationError("APK 파일을 열 수 없습니다")
    with zf:
        names = zf.namelist()
        if "AndroidManifest.xml" not in names:
            raise ValidationError("AndroidManifest.xml 이 없어 APK가 아닙니다")
        v1_signed = any(re.fullmatch(r"META-INF/[^/]+\.(RSA|DSA|EC)", n) for n in names)
    v2_signed = b"APK Sig Block 42" in _tail(path, 4 * 1024 * 1024)
    if not (v1_signed or v2_signed):
        raise ValidationError("서명되지 않은 APK입니다. release 또는 debug 서명된 APK를 올려주세요")
    try:
        from pyaxmlparser import APK

        apk = APK(str(path))
        package = apk.package
    except Exception:
        raise ValidationError("APK에서 패키지명을 추출할 수 없습니다")
    if not package:
        raise ValidationError("APK에서 패키지명을 추출할 수 없습니다")
    return ApkInfo(package=package, version_name=apk.version_name or "", version_code=str(apk.version_code or ""))


def _tail(path: Path, size: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(0, 2)
        end = f.tell()
        f.seek(max(0, end - size))
        return f.read()


TESTFLIGHT_RE = re.compile(r"^https://testflight\.apple\.com/join/[A-Za-z0-9]{6,12}/?$")
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}


def check_testflight(url: str) -> str:
    url = url.strip()
    if not TESTFLIGHT_RE.match(url):
        raise ValidationError("TestFlight 공개 링크(https://testflight.apple.com/join/...)를 넣어주세요")
    return url.rstrip("/")


def check_video(filename: str, path: Path) -> str:
    """확장자와 파일 앞부분(매직 바이트)으로 영상인지 확인하고 확장자를 돌려준다."""
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise ValidationError("시연 영상은 mp4, webm, mov 만 올릴 수 있습니다")
    with open(path, "rb") as f:
        head = f.read(12)
    is_mp4_family = head[4:8] == b"ftyp"          # mp4, mov
    is_webm = head[:4] == b"\x1a\x45\xdf\xa3"     # Matroska/WebM
    if not (is_mp4_family or is_webm):
        raise ValidationError("영상 파일이 아니거나 손상됐습니다")
    return suffix


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def check_image(filename: str, size: int, max_bytes: int) -> None:
    if Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
        raise ValidationError(f"이미지 형식이 아닙니다: {filename}")
    if size > max_bytes:
        raise ValidationError(f"이미지는 각 {max_bytes // 1024 // 1024}MB 이하여야 합니다: {filename}")


GITHUB_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


def check_repo(url: str, branch: str) -> None:
    if not GITHUB_RE.match(url):
        raise ValidationError("GitHub 공개 저장소 https 주소만 받을 수 있습니다 (https://github.com/아이디/저장소)")
    if not BRANCH_RE.match(branch) or branch.startswith("-") or ".." in branch:
        raise ValidationError("브랜치 이름이 올바르지 않습니다")


# ---- 링크 이름 (slug) ----

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
RESERVED_SLUGS = {"api", "admin", "assets", "static", "public", "upload", "students", "_expo", "favicon"}


def check_slug(slug: str, own_student_no: str) -> None:
    if not SLUG_RE.match(slug) or "--" in slug:
        raise ValidationError(
            "링크 이름은 영문 소문자·숫자·하이픈(-)으로 1~32자, 하이픈으로 시작·끝날 수 없습니다",
            code="SLUG_INVALID",
        )
    if slug in RESERVED_SLUGS:
        raise ValidationError("예약된 이름이라 쓸 수 없습니다", code="SLUG_INVALID")
    # 다른 학생의 학번과 헷갈리지 않게 숫자 4자리는 본인 학번만 허용
    if re.fullmatch(r"\d{4}", slug) and slug != own_student_no:
        raise ValidationError("숫자 4자리는 본인 학번만 쓸 수 있습니다", code="SLUG_INVALID")
