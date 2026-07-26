from datetime import datetime, timezone

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


def test_fallback_groups_named_aesthetics_and_marks_unverified():
    articles = [
        make_article("Cottagecore looks return to the runway"),
        make_article("Another cottagecore moment on TikTok"),
        make_article("Unrelated trend-adjacent story"),
    ]
    analysis = _fallback_analysis(articles)
    names = [t.working_name for t in analysis.trends]
    assert "Cottagecore" in names
    assert all(not t.verified for t in analysis.trends)
    assert all(t.confidence == 1 for t in analysis.trends)


def test_analyze_uses_fallback_without_api_key():
    articles = [make_article("Cottagecore looks return to the runway")]
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
                "silhouette": "s",
                "proportions": "p",
                "color": "c",
                "material": "m",
                "detail": "d",
                "styling": "st",
                "earliest_occurrences": "e",
                "designers": ["Designer A"],
                "celebrities": [],
                "subcultures": [],
                "platforms": [],
                "cultural_context": "ctx",
                "stage": "growth",
                "confirming_evidence": [
                    {"text": "evidence", "source_indices": [0, 99]},  # 99 out of range
                ],
                "contradicting_evidence": "none found",
                "predicted_horizon": "soon",
                "marketing_implication": "act now",
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
