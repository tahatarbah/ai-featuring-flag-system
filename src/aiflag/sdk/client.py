from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from aiflag.engine import (
    Evaluation,
    FlagSnapshot,
    RuleSnapshot,
    VariantSnapshot,
    evaluate,
)

log = logging.getLogger(__name__)


class AIFlags:
    """Local-evaluating client. Polls config; fail-open on last cache."""

    def __init__(
        self,
        sdk_key: str,
        api_url: str = "http://127.0.0.1:8010",
        poll_seconds: int = 10,
        start_polling: bool = True,
    ) -> None:
        self.sdk_key = sdk_key
        self.api_url = api_url.rstrip("/")
        self.poll_seconds = poll_seconds
        self._flags: dict[str, FlagSnapshot] = {}
        self._has_cache = False
        self._buffer: dict[str, list] = {"impressions": [], "generations": [], "quality": []}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if start_polling:
            self.refresh()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self.flush()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.sdk_key}"}

    def refresh(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.api_url}/sdk/v1/config", headers=self._headers())
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            log.warning("config poll failed: %s", exc)
            return False
        flags: dict[str, FlagSnapshot] = {}
        for key, raw in (payload.get("flags") or {}).items():
            flags[key] = FlagSnapshot(
                key=raw["key"],
                flag_type=raw.get("flag_type", "multivariate"),
                status=raw.get("status", "draft"),
                kill_switch=bool(raw.get("kill_switch")),
                salt=raw.get("salt", ""),
                archived=bool(raw.get("archived")),
                percentage_bps=int(raw.get("percentage_bps") or 0),
                variants=[
                    VariantSnapshot(
                        key=v["key"],
                        is_control=bool(v.get("is_control")),
                        payload=dict(v.get("payload") or {}),
                    )
                    for v in raw.get("variants") or []
                ],
                rules=[
                    RuleSnapshot(
                        priority=int(r.get("priority") or 0),
                        attribute=r["attribute"],
                        op=r["op"],
                        value=r["value"],
                        variant_key=r["variant_key"],
                    )
                    for r in raw.get("rules") or []
                ],
            )
        with self._lock:
            self._flags = flags
            self._has_cache = True
        return True

    def load_config(self, payload: dict[str, Any]) -> None:
        """Test helper: inject a config document without HTTP."""
        flags: dict[str, FlagSnapshot] = {}
        for key, raw in (payload.get("flags") or {}).items():
            flags[key] = FlagSnapshot(
                key=raw["key"],
                flag_type=raw.get("flag_type", "multivariate"),
                status=raw.get("status", "active"),
                kill_switch=bool(raw.get("kill_switch")),
                salt=raw.get("salt", "s"),
                archived=bool(raw.get("archived")),
                percentage_bps=int(raw.get("percentage_bps") or 0),
                variants=[
                    VariantSnapshot(
                        key=v["key"],
                        is_control=bool(v.get("is_control")),
                        payload=dict(v.get("payload") or {}),
                    )
                    for v in raw.get("variants") or []
                ],
                rules=[],
            )
        with self._lock:
            self._flags = flags
            self._has_cache = True

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            self.refresh()
            self.flush()

    def evaluate(self, flag_key: str, user_key: str, attributes: dict | None = None) -> Evaluation:
        with self._lock:
            flag = self._flags.get(flag_key)
            has_cache = self._has_cache
        if flag is None and not has_cache:
            return Evaluation(flag_key=flag_key, variant_key="off", payload={}, reason="FLAG_NOT_FOUND")
        result = evaluate(flag, user_key, attributes)
        self._buffer["impressions"].append(
            {
                "flag_key": result.flag_key,
                "user_key": user_key,
                "variant_key": result.variant_key,
                "reason": result.reason,
            }
        )
        if len(self._buffer["impressions"]) >= 50:
            self.flush()
        return result

    def variation(self, flag_key: str, user_key: str, attributes: dict | None = None) -> dict[str, Any]:
        return self.evaluate(flag_key, user_key, attributes).payload

    def track_generation(
        self,
        flag_key: str,
        user_key: str,
        variant_key: str,
        *,
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error_code: str | None = None,
        model: str = "",
    ) -> None:
        self._buffer["generations"].append(
            {
                "flag_key": flag_key,
                "user_key": user_key,
                "variant_key": variant_key,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "error_code": error_code,
                "model": model,
            }
        )
        if len(self._buffer["generations"]) >= 50:
            self.flush()

    def track_quality(
        self,
        flag_key: str,
        user_key: str,
        variant_key: str,
        score: float,
        source: str = "thumbs",
        comment: str = "",
    ) -> None:
        self._buffer["quality"].append(
            {
                "flag_key": flag_key,
                "user_key": user_key,
                "variant_key": variant_key,
                "score": score,
                "source": source,
                "comment": comment,
            }
        )

    def flush(self) -> None:
        with self._lock:
            payload = {
                "impressions": list(self._buffer["impressions"]),
                "generations": list(self._buffer["generations"]),
                "quality": list(self._buffer["quality"]),
            }
            self._buffer = {"impressions": [], "generations": [], "quality": []}
        if not any(payload.values()):
            return
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{self.api_url}/sdk/v1/events",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            log.warning("event flush failed: %s", exc)
            with self._lock:
                for key in payload:
                    self._buffer[key] = payload[key] + self._buffer[key]
