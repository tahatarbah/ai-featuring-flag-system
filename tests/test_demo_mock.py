import pytest

from aiflag.config import settings
from aiflag.demo.ollama import generate_answer, judge_answer


@pytest.mark.asyncio
async def test_mock_generate_when_ollama_down(monkeypatch):
    monkeypatch.setattr(settings, "demo_mock_llm", True)
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:9")
    result = await generate_answer(
        {
            "model": "llama3.2",
            "prompt_id": "support_v2",
            "system_prompt": "cautious assistant",
        },
        "migrations stuck",
    )
    assert result.error_code is None
    assert "mock" in result.model
    assert "Checklist" in result.answer or "would not guess" in result.answer


@pytest.mark.asyncio
async def test_mock_judge_scores_treatment_higher(monkeypatch):
    monkeypatch.setattr(settings, "demo_mock_llm", True)
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:9")
    control = await judge_answer("q", "(mock control / support_v1) short tip")
    treatment = await judge_answer(
        "q",
        "(mock treatment / support_v2) I would not guess. Checklist for: q\n1) a\n2) b",
    )
    assert treatment.score > control.score
