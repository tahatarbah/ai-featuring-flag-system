"""Hit the playground as many sticky users so quality charts fill with both arms."""
from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8010"
ADMIN = {"Authorization": "Bearer dev-admin-token", "Content-Type": "application/json"}
QUESTION = "Our staging deploy is stuck on migrations. What should I check first?"


def ask(user: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/v1/demo/ask",
        data=json.dumps({"user_key": user, "question": QUESTION}).encode(),
        headers=ADMIN,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    users = [f"user-{i:03d}" for i in range(40)] + ["alice", "bob", "carol", "dave"]
    counts: dict[str, int] = {}
    for user in users:
        body = ask(user)
        variant = body["evaluation"]["variant_key"]
        counts[variant] = counts.get(variant, 0) + 1
        assert body.get("error_code") is None, body
        assert body.get("answer"), body
        assert body.get("judge_score") is not None, body
    print("traffic ok", counts)


if __name__ == "__main__":
    main()
