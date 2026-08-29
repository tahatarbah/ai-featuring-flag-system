from aiflag.sdk import AIFlags


def test_sdk_fail_open_uses_cache():
    client = AIFlags(sdk_key="x", api_url="http://127.0.0.1:9", start_polling=False)
    client.load_config(
        {
            "flags": {
                "support_assistant": {
                    "key": "support_assistant",
                    "status": "active",
                    "kill_switch": False,
                    "salt": "s",
                    "percentage_bps": 10000,
                    "variants": [
                        {"key": "control", "is_control": True, "payload": {"v": 1}},
                        {"key": "treatment", "is_control": False, "payload": {"v": 2}},
                    ],
                }
            }
        }
    )
    # Point at a dead API; cache must still evaluate.
    result = client.evaluate("support_assistant", "alice")
    assert result.variant_key == "treatment"
    assert result.payload["v"] == 2


def test_sdk_without_cache_returns_not_found():
    client = AIFlags(sdk_key="x", api_url="http://127.0.0.1:9", start_polling=False)
    result = client.evaluate("missing", "alice")
    assert result.reason == "FLAG_NOT_FOUND"
