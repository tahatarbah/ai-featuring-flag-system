from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from aiflag.config import settings


@dataclass
class GenerateResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    model: str
    error_code: str | None = None


@dataclass
class JudgeResult:
    score: float
    reason: str


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _mock_generate(payload: dict, question: str, model: str) -> GenerateResult:
    """Local fallback when Ollama is not installed — still drives flags + quality gates."""
    prompt_id = str(payload.get("prompt_id") or "support_v1")
    cautious = "v2" in prompt_id or "cautious" in str(payload.get("system_prompt") or "").lower()
    if cautious:
        answer = (
            f"(mock treatment / {prompt_id}) I would not guess. Confirm which migration is stuck, "
            f"check the lock table, and restore from the last good backup before retrying.\n\n"
            f"Checklist for: {question[:120]}\n"
            "1) Identify the failing revision\n"
            "2) Verify no concurrent writers\n"
            "3) Roll forward only after a dry-run"
        )
        tokens_out = 90
        latency_ms = 180
    else:
        answer = (
            f"(mock control / {prompt_id}) Check the latest migration status, restart the worker, "
            f"and retry. For “{question[:80]}”, look at logs first and unblock the queue."
        )
        tokens_out = 55
        latency_ms = 120
    tokens_in = max(12, len(question) // 4)
    return GenerateResult(
        answer=answer,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=f"mock:{model}",
        error_code=None,
    )


def _mock_judge(question: str, answer: str) -> JudgeResult:
    if not answer.strip():
        return JudgeResult(score=1.0, reason="empty answer")
    score = 3.5
    if "Checklist" in answer or "would not guess" in answer:
        score = 4.4
    elif "mock control" in answer:
        score = 3.6
    if len(answer) < 40:
        score = min(score, 2.5)
    if "password" in answer.lower() or "secret" in answer.lower():
        score = 1.5
    return JudgeResult(score=score, reason="mock judge (install Ollama for real scores)")


async def generate_answer(payload: dict, question: str) -> GenerateResult:
    model = str(payload.get("model") or settings.ollama_model)
    system = str(payload.get("system_prompt") or "You are a helpful support assistant.")
    temperature = float(payload.get("temperature") or 0.2)
    max_tokens = int(payload.get("max_tokens") or 512)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": question},
                    ],
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError:
        if settings.demo_mock_llm:
            return _mock_generate(payload, question, model)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return GenerateResult(
            answer="",
            latency_ms=latency_ms,
            tokens_in=0,
            tokens_out=0,
            model=model,
            error_code="ollama_unavailable",
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    message = (body.get("message") or {}).get("content") or ""
    tokens_in = int(body.get("prompt_eval_count") or 0)
    tokens_out = int(body.get("eval_count") or 0)
    return GenerateResult(
        answer=message,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=model,
    )


async def judge_answer(question: str, answer: str) -> JudgeResult:
    prompt = (
        "You score a support assistant reply. Return JSON only: "
        '{"score": <number 1-5>, "reason": "<short reason>"}. '
        "5 is excellent, helpful, and safe. 1 is wrong, harmful, or empty.\n\n"
        f"Question: {question}\n\nAnswer: {answer}"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.ollama_judge_model,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"temperature": 0.0, "num_predict": 200},
                },
            )
            response.raise_for_status()
            body = response.json()
        text = (body.get("message") or {}).get("content") or ""
        parsed = _extract_json(text)
        score = float(parsed.get("score", 3))
        score = max(1.0, min(5.0, score))
        return JudgeResult(score=score, reason=str(parsed.get("reason") or ""))
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
        if settings.demo_mock_llm:
            return _mock_judge(question, answer)
        return JudgeResult(score=3.0, reason="judge_unavailable")
