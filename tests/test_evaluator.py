from app.services.evaluator import parse_evaluation


def test_parse_normal_json():
    ev = parse_evaluation(
        '{"score": 85, "strengths": ["a", "b"], "weaknesses": ["c"], '
        '"tags": ["x"], "suggestion": "s", "summary": "sum"}'
    )
    assert ev.score == 85.0
    assert ev.strengths == ["a", "b"]
    assert ev.weaknesses == ["c"]
    assert ev.tags == ["x"]
    assert ev.suggestion == "s"
    assert ev.summary == "sum"


def test_parse_fenced_code_block():
    ev = parse_evaluation("```json\n{\"score\": 90}\n```")
    assert ev.score == 90.0


def test_parse_fallback_on_invalid_text():
    ev = parse_evaluation("完全不是 JSON")
    assert ev.score == 0.0
    assert ev.summary == "完全不是 JSON"


def test_parse_clamps_score():
    assert parse_evaluation('{"score": 150}').score == 100.0
    assert parse_evaluation('{"score": -10}').score == 0.0


def test_parse_string_to_list():
    ev = parse_evaluation('{"score": 70, "strengths": "只有一个", "tags": []}')
    assert ev.strengths == ["只有一个"]
    assert ev.tags == []


def test_evaluate_mock_when_no_key():
    from app.services.evaluator import evaluate_answer
    from app.services.llm_config import LLMConfig

    ev = evaluate_answer("c", "q", "a", "", "answer", LLMConfig("deepseek", "", "https://x", "m"))
    assert ev.source == "mock"
    assert ev.warning == ""
    assert ev.parsed is False


def test_evaluate_marks_llm_when_parseable(monkeypatch):
    from app.config import settings
    from app.services import evaluator
    from app.services.llm_config import LLMConfig

    monkeypatch.setattr(settings, "use_mock_evaluator", False)
    monkeypatch.setattr(
        evaluator.DeepSeekClient, "chat", lambda *a, **k: '{"score": 90, "summary": "s"}'
    )
    ev = evaluator.evaluate_answer(
        "c", "q", "a", "", "answer", LLMConfig("deepseek", "sk-x", "https://x", "m")
    )
    assert ev.source == "llm"
    assert ev.parsed is True
    assert ev.score == 90.0


def test_evaluate_degraded_on_llm_failure(monkeypatch):
    """大模型调用失败时必须显式标注降级，而不是静默返回 mock。"""
    from app.config import settings
    from app.services import evaluator
    from app.services.deepseek import DeepSeekError
    from app.services.llm_config import LLMConfig

    monkeypatch.setattr(settings, "use_mock_evaluator", False)

    def boom(*a, **k):
        raise DeepSeekError("nope")

    monkeypatch.setattr(evaluator.DeepSeekClient, "chat", boom)
    ev = evaluator.evaluate_answer(
        "c", "q", "a", "", "answer", LLMConfig("deepseek", "sk-x", "https://x", "m")
    )
    assert ev.source == "mock_fallback"
    assert ev.warning
    assert ev.parsed is False


def test_evaluate_degraded_on_unparsable_output(monkeypatch):
    from app.config import settings
    from app.services import evaluator
    from app.services.llm_config import LLMConfig

    monkeypatch.setattr(settings, "use_mock_evaluator", False)
    monkeypatch.setattr(evaluator.DeepSeekClient, "chat", lambda *a, **k: "not json at all")
    ev = evaluator.evaluate_answer(
        "c", "q", "a", "", "answer", LLMConfig("deepseek", "sk-x", "https://x", "m")
    )
    assert ev.source == "mock_fallback"
    assert ev.parsed is False
