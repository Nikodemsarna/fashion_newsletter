from datetime import datetime, timezone

import requests

from fashion_trends import analyze as analyze_module
from fashion_trends.analyze import (
    Settings,
    _fallback_analysis,
    _payload_to_analysis,
    analyze,
)
from fashion_trends.fetch import Article

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def make_article(title, summary="", source="Src", link=None):
    return Article(
        title=title,
        link=link or f"https://example.com/{title}",
        source=source,
        summary=summary,
        published=NOW,
    )


def test_fallback_groups_named_phenomena_and_marks_unverified():
    articles = [
        make_article("Brand safety debate returns to the agenda"),
        make_article("Another brand safety moment on LinkedIn"),
        make_article("Unrelated trend-adjacent story"),
    ]
    analysis = _fallback_analysis(articles)
    names = [t.working_name for t in analysis.trends]
    assert "Brand Safety" in names
    assert all(not t.verified for t in analysis.trends)
    assert all(t.confidence == 1 for t in analysis.trends)


def test_analyze_uses_fallback_without_api_key():
    articles = [make_article("Retail media keeps growing its ad budget share")]
    settings = Settings()  # no keys set
    analysis = analyze(articles, settings)
    assert analysis.trends
    assert not analysis.trends[0].verified


def test_payload_to_analysis_clamps_confidence_and_filters_bad_indices():
    data = {
        "intro": "Test intro",
        "trends": [
            {
                "working_name": "Test Trend",
                "mechanic": "m",
                "channel": "c",
                "tone": "t",
                "target_audience": "a",
                "creative_hook": "h",
                "measurement_signal": "ms",
                "earliest_occurrences": "e",
                "brands": ["Brand A"],
                "agencies": [],
                "voices": [],
                "platforms": [],
                "cultural_context": "ctx",
                "stage": "growth",
                "confirming_evidence": [
                    {"text": "evidence", "source_indices": [0, 99]},  # 99 out of range
                ],
                "contradicting_evidence": "none found",
                "predicted_horizon": "soon",
                "business_implication": "act now",
                "confidence": 9,  # out of range, should clamp to 5
            },
            {"working_name": "", "stage": "growth"},  # missing name -> dropped
        ],
    }
    analysis = _payload_to_analysis(data, n_articles=1, max_trends=8)
    assert len(analysis.trends) == 1
    t = analysis.trends[0]
    assert t.confidence == 5
    assert t.confirming_evidence[0].source_indices == [0]
    assert t.stage == "growth"


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def test_analyze_retries_transient_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(analyze_module.time, "sleep", lambda _seconds: None)

    calls = {"n": 0}

    def flaky_gemini(prompt, settings):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error(503)
        return {"intro": "ok", "trends": []}

    monkeypatch.setattr(analyze_module, "_call_gemini", flaky_gemini)

    settings = Settings(provider="gemini", gemini_api_key="x")
    articles = [make_article("Some trend story")]
    result = analyze(articles, settings)

    assert calls["n"] == 2
    assert result.intro == "ok"


def test_analyze_gives_up_after_max_attempts_on_repeated_503(monkeypatch):
    monkeypatch.setattr(analyze_module.time, "sleep", lambda _seconds: None)

    calls = {"n": 0}

    def always_503(prompt, settings):
        calls["n"] += 1
        raise _http_error(503)

    monkeypatch.setattr(analyze_module, "_call_gemini", always_503)

    settings = Settings(provider="gemini", gemini_api_key="x")
    articles = [make_article("Some trend story")]
    result = analyze(articles, settings)

    assert calls["n"] == analyze_module._MAX_ATTEMPTS
    assert not result.trends[0].verified


def test_analyze_does_not_retry_auth_error(monkeypatch):
    monkeypatch.setattr(analyze_module.time, "sleep", lambda _seconds: None)

    calls = {"n": 0}

    def failing_gemini(prompt, settings):
        calls["n"] += 1
        raise _http_error(401)

    monkeypatch.setattr(analyze_module, "_call_gemini", failing_gemini)

    settings = Settings(provider="gemini", gemini_api_key="x")
    articles = [make_article("Some trend story")]
    result = analyze(articles, settings)

    assert calls["n"] == 1
    assert "błąd autoryzacji" in result.intro


def test_analyze_falls_over_to_secondary_provider_after_primary_exhausted(monkeypatch):
    monkeypatch.setattr(analyze_module.time, "sleep", lambda _seconds: None)

    gemini_calls = {"n": 0}
    groq_calls = {"n": 0}

    def always_503_gemini(prompt, settings):
        gemini_calls["n"] += 1
        raise _http_error(503)

    def working_groq(prompt, settings):
        groq_calls["n"] += 1
        return {"intro": "from groq", "trends": []}

    monkeypatch.setattr(analyze_module, "_call_gemini", always_503_gemini)
    monkeypatch.setattr(analyze_module, "_call_groq", working_groq)

    settings = Settings(provider="gemini", gemini_api_key="x", groq_api_key="g")
    articles = [make_article("Some trend story")]
    result = analyze(articles, settings)

    assert gemini_calls["n"] == analyze_module._MAX_ATTEMPTS
    assert groq_calls["n"] == 1
    assert result.intro == "from groq"


def test_analyze_skips_fallback_provider_when_model_is_forced(monkeypatch):
    monkeypatch.setattr(analyze_module.time, "sleep", lambda _seconds: None)

    groq_calls = {"n": 0}

    def always_503_gemini(prompt, settings):
        raise _http_error(503)

    def working_groq(prompt, settings):
        groq_calls["n"] += 1
        return {"intro": "from groq", "trends": []}

    monkeypatch.setattr(analyze_module, "_call_gemini", always_503_gemini)
    monkeypatch.setattr(analyze_module, "_call_groq", working_groq)

    settings = Settings(
        provider="gemini", gemini_api_key="x", groq_api_key="g", model="a-forced-model"
    )
    articles = [make_article("Some trend story")]
    result = analyze(articles, settings)

    assert groq_calls["n"] == 0
    assert not result.trends[0].verified
