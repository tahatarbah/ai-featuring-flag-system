from fastapi.testclient import TestClient

from aiflag.api.main import app
from aiflag.config import settings

settings.gate_enabled = False


def test_health_includes_service():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["service"] == "warden"


def test_system_routes_require_admin():
    with TestClient(app) as client:
        assert client.get("/api/v1/system/status").status_code == 401
        assert client.get("/api/v1/overview").status_code == 401
        assert client.post("/api/v1/evaluate", json={"flag_key": "x", "user_key": "u"}).status_code == 401
