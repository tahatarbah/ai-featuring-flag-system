from fastapi.testclient import TestClient

from aiflag.api.main import app
from aiflag.config import settings
from aiflag.engine import evaluate, snapshot_from_orm
from aiflag.models import Flag, FlagVariant, Rollout

settings.gate_enabled = False


def test_health_unauthenticated():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_admin_requires_token():
    with TestClient(app) as client:
        res = client.get("/api/v1/flags")
        assert res.status_code == 401


def test_kill_switch_engine_path():
    flag = Flag(
        key="k",
        name="k",
        status="active",
        kill_switch=True,
        salt="s",
    )
    flag.variants = [
        FlagVariant(key="control", is_control=True, payload={"on": False}),
        FlagVariant(key="on", is_control=False, payload={"on": True}),
    ]
    flag.rules = []
    flag.rollout = Rollout(percentage_bps=10000, stage=5, auto_advance=False)
    result = evaluate(snapshot_from_orm(flag), "user-1")
    assert result.reason == "KILL_SWITCH"
    assert result.variant_key == "control"
