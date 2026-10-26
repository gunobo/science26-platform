import stat
import zipfile
from pathlib import Path

import pytest
import yaml

from app.services import validation as v
from app.services.compose import rewrite, static_compose, traefik_labels


def make_zip(path: Path, files: dict[str, str], symlink: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return path


def test_safe_extract_ok(tmp_path):
    z = make_zip(tmp_path / "a.zip", {"dist/index.html": "<html></html>", "dist/a.js": "x"})
    v.safe_extract(z, tmp_path / "out", 10**9)
    assert v.find_root(tmp_path / "out", "index.html") == tmp_path / "out" / "dist"


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../evil"])
def test_safe_extract_rejects_slip(tmp_path, name):
    z = make_zip(tmp_path / "a.zip", {name: "x"})
    with pytest.raises(v.ValidationError):
        v.safe_extract(z, tmp_path / "out", 10**9)


def test_safe_extract_rejects_symlink(tmp_path):
    z = make_zip(tmp_path / "a.zip", {"index.html": "x"}, symlink="link")
    with pytest.raises(v.ValidationError, match="심볼릭"):
        v.safe_extract(z, tmp_path / "out", 10**9)


def test_safe_extract_rejects_bomb(tmp_path):
    z = make_zip(tmp_path / "a.zip", {"big.txt": "0" * 5000})
    with pytest.raises(v.ValidationError, match="1GB"):
        v.safe_extract(z, tmp_path / "out", 1000)


def test_find_root_missing(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with pytest.raises(v.ValidationError):
        v.find_root(tmp_path, "index.html")


def test_absolute_paths():
    html = '<script src="/assets/app.js"></script><link href="./a.css"><a href="//cdn.x/y"></a><img src="/logo.png">'
    assert v.find_absolute_paths(html) == ["/assets/app.js", "/logo.png"]


def _project(tmp_path: Path, compose: dict) -> Path:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "Dockerfile").write_text("FROM node:20")
    text = yaml.safe_dump(compose)
    (tmp_path / "docker-compose.yml").write_text(text)
    return tmp_path


GOOD = {
    "services": {
        "web": {"build": "./web", "expose": ["3000"], "labels": ["science26.public=true"]},
        "api": {"image": "node:20-alpine", "command": "node a.js", "expose": [8000],
                "labels": {"science26.api": "true"}, "environment": {"A": "1"}},
    }
}


def test_parse_compose_ok(tmp_path):
    root = _project(tmp_path, GOOD)
    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    assert spec.public == "web" and spec.api == "api"
    assert spec.ports == {"web": 3000, "api": 8000}


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"ports": ["80:80"]}, "금지"),
        ({"volumes": ["/:/host"]}, "금지"),
        ({"privileged": True}, "금지"),
        ({"network_mode": "host"}, "금지"),
        ({"restart": "always"}, "허용되지 않는 키"),
    ],
)
def test_parse_compose_forbidden(tmp_path, patch, match):
    compose = {"services": {"web": {**GOOD["services"]["web"], **patch}}}
    root = _project(tmp_path, compose)
    with pytest.raises(v.ValidationError, match=match) as e:
        v.parse_compose((root / "docker-compose.yml").read_text(), root)
    assert e.value.code == "COMPOSE_FORBIDDEN_KEY"


@pytest.mark.parametrize("image", ["postgres:16", "redis:7", "someone/app:latest", "ghcr.io/x/y"])
def test_parse_compose_bad_images(tmp_path, image):
    compose = {"services": {"web": {"image": image, "labels": ["science26.public=true"]}}}
    root = _project(tmp_path, compose)
    with pytest.raises(v.ValidationError):
        v.parse_compose((root / "docker-compose.yml").read_text(), root)


def test_parse_compose_context_escape(tmp_path):
    compose = {"services": {"web": {"build": "../", "labels": ["science26.public=true"]}}}
    root = _project(tmp_path, compose)
    with pytest.raises(v.ValidationError, match="context"):
        v.parse_compose((root / "docker-compose.yml").read_text(), root)


def test_parse_compose_needs_public(tmp_path):
    compose = {"services": {"a": {"image": "nginx"}, "b": {"image": "node"}}}
    root = _project(tmp_path, compose)
    with pytest.raises(v.ValidationError, match="science26.public"):
        v.parse_compose((root / "docker-compose.yml").read_text(), root)


def test_parse_compose_too_many(tmp_path):
    compose = {"services": {f"s{i}": {"image": "nginx"} for i in range(4)}}
    root = _project(tmp_path, compose)
    with pytest.raises(v.ValidationError, match="최대"):
        v.parse_compose((root / "docker-compose.yml").read_text(), root)


def test_rewrite(tmp_path):
    root = _project(tmp_path, GOOD)
    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    out = rewrite(
        spec, root=root, student_no="1411", slug="space-runner", version=3, seq=7,
        env={"DATABASE_URL": "pg://x", "BASE_PATH": "/students/space-runner"},
        public_host="science26.bssm.dev", edge_network="s26-edge",
        memory_mb=256, stack_memory_mb=512, cpus=0.5, pids=128,
    )
    assert out["name"] == "stu-1411-v3"
    web, api = out["services"]["web"], out["services"]["api"]
    assert web["image"] == "s26/stu-1411-web:v3"
    assert web["build"]["context"] == str((root / "web").resolve())
    assert web["mem_limit"] == "256m" and web["cap_drop"] == ["ALL"] and web["read_only"] is True
    assert "edge" in web["networks"] and "edge" in api["networks"]
    assert web["labels"]["traefik.http.routers.stu-1411-v3.rule"] == (
        "Host(`science26.bssm.dev`) && PathPrefix(`/students/space-runner`)"
    )
    assert web["labels"]["traefik.http.routers.stu-1411-v3.priority"] == "1007"
    assert api["labels"]["traefik.http.routers.stu-1411-v3-api.priority"] == "1000007"
    assert api["environment"] == {"A": "1", "DATABASE_URL": "pg://x", "BASE_PATH": "/students/space-runner"}
    assert out["networks"]["default"] == {"name": "stu-1411-net", "external": True}


def test_rewrite_strips_student_traefik_labels(tmp_path):
    compose = {"services": {"web": {"image": "nginx", "labels": {
        "science26.public": "true", "traefik.http.routers.evil.rule": "Host(`science26-upload.bssm.dev`)"}}}}
    root = _project(tmp_path, compose)
    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    out = rewrite(spec, root=root, student_no="1411", slug="1411", version=1, seq=1, env={},
                  public_host="h", edge_network="e", memory_mb=256, stack_memory_mb=512, cpus=0.5, pids=128)
    assert not any("evil" in k for k in out["services"]["web"]["labels"])


def test_memory_split():
    compose_spec = v.ComposeSpec(services={"a": {"image": "nginx"}, "b": {"image": "node"}, "c": {"image": "node"}},
                                 public="a", ports={"a": 80, "b": 80, "c": 80})
    out = rewrite(compose_spec, root=Path("/tmp"), student_no="1411", slug="x", version=1, seq=1, env={},
                  public_host="h", edge_network="e", memory_mb=256, stack_memory_mb=512, cpus=0.5, pids=128)
    assert all(s["mem_limit"] == "170m" for s in out["services"].values())


def test_static_compose(tmp_path):
    out = static_compose(student_no="1411", slug="game", version=2, seq=5, context=tmp_path,
                         public_host="h", edge_network="e", memory_mb=256, cpus=0.5, pids=128)
    web = out["services"]["web"]
    assert web["labels"]["traefik.http.services.stu-1411-v2.loadbalancer.server.port"] == "8080"
    assert "slash" in web["labels"]["traefik.http.routers.stu-1411-v2.middlewares"]


def test_traefik_labels_api_has_no_slash_redirect():
    labels = traefik_labels("1411", "game", 1, 1, "h", "e", 8000, api=True)
    assert labels["traefik.http.routers.stu-1411-v1-api.middlewares"] == "stu-1411-v1-api-strip"


@pytest.mark.parametrize("slug,ok", [
    ("space-runner", True), ("1411", True), ("a", True), ("1234", False), ("Space", False),
    ("-x", False), ("x-", False), ("a--b", False), ("api", False), ("한글", False), ("a" * 33, False),
])
def test_check_slug(slug, ok):
    if ok:
        v.check_slug(slug, "1411")
    else:
        with pytest.raises(v.ValidationError):
            v.check_slug(slug, "1411")


@pytest.mark.parametrize("url,branch,ok", [
    ("https://github.com/a/b", "main", True),
    ("https://github.com/a/b.git", "feature/x", True),
    ("http://github.com/a/b", "main", False),
    ("https://gitlab.com/a/b", "main", False),
    ("https://github.com/a/b", "--upload-pack=x", False),
    ("https://github.com/a/b", "a..b", False),
])
def test_check_repo(url, branch, ok):
    if ok:
        v.check_repo(url, branch)
    else:
        with pytest.raises(v.ValidationError):
            v.check_repo(url, branch)


def test_inspect_apk_unsigned(tmp_path):
    z = make_zip(tmp_path / "a.apk", {"AndroidManifest.xml": "x", "classes.dex": "x"})
    with pytest.raises(v.ValidationError, match="서명"):
        v.inspect_apk(z)


def test_login_allowlist(monkeypatch):
    from app.config import get_settings
    from app.routers.auth import is_allowed

    monkeypatch.setenv("ALLOWED_GOOGLE_DOMAINS", "bssm.hs.kr")
    monkeypatch.setenv("ADMIN_EMAILS", "Teacher@Gmail.com")
    get_settings.cache_clear()
    try:
        assert is_allowed("s1@bssm.hs.kr", "bssm.hs.kr")
        assert is_allowed("teacher@gmail.com", None)
        assert not is_allowed("someone@gmail.com", None)
        assert not is_allowed("s1@bssm.hs.kr", None)  # hd 없는 계정은 학교 계정이 아님
    finally:
        get_settings.cache_clear()
