from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import validation as v
from app.services.compose import rewrite, static_compose

H = {"X-S26-Request": "1"}
UPLOAD = "https://upload.science26.bssm.dev"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_get_is_not_blocked(client):
    assert client.get("/api/health").status_code == 200


def test_unsafe_without_csrf_header_rejected(client):
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403


@pytest.mark.parametrize("headers", [
    {"Origin": "https://science26.bssm.dev"},          # 학생 페이지 출처
    {"Sec-Fetch-Site": "same-site"},                    # 같은 사이트의 다른 출처
    {"Sec-Fetch-Site": "cross-site"},
    {"Origin": "https://evil.example"},
])
def test_cross_origin_rejected_even_with_header(client, headers):
    assert client.post("/api/v1/auth/logout", headers={**H, **headers}).status_code == 403


def test_same_origin_with_header_passes(client):
    r = client.post("/api/v1/auth/logout", headers={**H, "Origin": UPLOAD, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_oversized_body_rejected_before_reading(client):
    r = client.post("/api/v1/projects/me/releases", headers={**H, "Content-Length": str(500 * 1024 * 1024)}, content=b"")
    assert r.status_code == 413


def test_small_api_body_limit(client):
    r = client.post("/api/v1/auth/logout", headers=H, content=b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_upload_without_session_rejected_before_body(client):
    r = client.post("/api/v1/projects/me/releases", headers=H, files={"file": ("a.zip", b"x" * 1000)}, data={"type": "static"})
    assert r.status_code == 401


def _project(tmp_path: Path, compose: dict) -> Path:
    import yaml
    (tmp_path / "docker-compose.yml").write_text(yaml.safe_dump(compose))
    return tmp_path


def test_student_labels_whitelisted(tmp_path):
    compose = {"services": {"web": {"image": "nginx", "labels": {
        "science26.public": "true", "science26.port": "8080",
        "com.docker.compose.project": "stu-9999-v1", "traefik.enable": "true", "anything": "x"}}}}
    root = _project(tmp_path, compose)
    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    out = rewrite(spec, root=root, student_no="1411", slug="x", version=1, seq=1, env={},
                  public_host="h", edge_network="e", memory_mb=256, stack_memory_mb=512, cpus=0.5, pids=128)
    labels = out["services"]["web"]["labels"]
    assert "com.docker.compose.project" not in labels and "anything" not in labels
    assert labels["science26.port"] == "8080"


def test_student_containers_have_log_limits(tmp_path):
    out = static_compose(student_no="1411", slug="x", version=1, seq=1, context=tmp_path,
                         public_host="h", edge_network="e", memory_mb=256, cpus=0.5, pids=128)
    assert out["services"]["web"]["logging"]["options"]["max-size"] == "5m"
