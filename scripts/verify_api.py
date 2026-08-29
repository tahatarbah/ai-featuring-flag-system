import json
import urllib.request

base = "http://127.0.0.1:8010"
admin = {"Authorization": "Bearer dev-admin-token"}
sdk = {"Authorization": "Bearer sdk_dev_warden_local"}


def req(method, path, headers=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}


status, health = req("GET", "/health")
assert status == 200 and health["status"] == "ok", health

status, flags = req("GET", "/api/v1/flags", admin)
assert status == 200
keys = {f["key"] for f in flags}
assert keys == {"support_assistant", "show_confidence"}, keys
support = next(f for f in flags if f["key"] == "support_assistant")
assert support["status"] == "active"
assert support["rollout"]["percentage_bps"] == 2500

status, cfg = req("GET", "/sdk/v1/config", sdk)
assert "support_assistant" in cfg["flags"]

status, ev = req(
    "POST",
    "/sdk/v1/evaluate",
    sdk,
    {"flag_key": "support_assistant", "user_key": "alice"},
)
assert ev["reason"] in {"PERCENTAGE_ROLLOUT", "DEFAULT"}
assert ev["variant_key"] in {"control", "treatment"}

status, ask = req(
    "POST",
    "/api/v1/demo/ask",
    admin,
    {"user_key": "alice", "question": "How do I reset a stuck migration?"},
)
assert status == 200
assert ask["error_code"] == "ollama_unavailable"
assert ask["evaluation"]["variant_key"] in {"control", "treatment"}

status, killed = req("POST", f"/api/v1/flags/{support['id']}/kill", admin)
assert killed["kill_switch"] is True
status, ev2 = req(
    "POST",
    "/sdk/v1/evaluate",
    sdk,
    {"flag_key": "support_assistant", "user_key": "alice"},
)
assert ev2["reason"] == "KILL_SWITCH"
assert ev2["variant_key"] == "control"

status, restored = req("POST", f"/api/v1/flags/{support['id']}/restore", admin)
status, published = req("POST", f"/api/v1/flags/{support['id']}/publish", admin)
assert published["status"] == "active"

status, quality = req("GET", f"/api/v1/flags/{support['id']}/quality", admin)
assert quality["flag_key"] == "support_assistant"

print("API verification ok")
print("  flags", keys)
print("  eval", ev)
print("  ask error", ask["error_code"])
print("  kill reason", ev2["reason"])
