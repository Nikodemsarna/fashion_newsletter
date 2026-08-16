from datetime import datetime, timedelta, timezone

from fashion_trends.fetch import Article
from fashion_trends.filter import (
    filter_articles,
    is_recent,
    matches_trend_signal,
)

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def make(title="", summary="", link="https://example.com/a", published=NOW, source="Src"):
    return Article(title=title, link=link, source=source, summary=summary, published=published)


def test_matches_keywords():
    assert matches_trend_signal(make(title="Brand safety debate returns to the agenda"))
    assert matches_trend_signal(make(title="This micro-trend is going viral on TikTok"))
    assert matches_trend_signal(make(summary="Retail media dominates ad budgets"))
    assert matches_trend_signal(make(title="De-influencing sees a resurgence"))


def test_does_not_match_unrelated():
    assert not matches_trend_signal(make(title="Retailer reports quarterly earnings"))
    assert not matches_trend_signal(make(title="Agency opens new regional office"))


def test_recency_window():
    window = timedelta(hours=30)
    assert is_recent(make(published=NOW - timedelta(hours=10)), window, now=NOW)
    assert not is_recent(make(published=NOW - timedelta(hours=40)), window, now=NOW)
    # Undated entries are kept.
    assert is_recent(make(published=None), window, now=NOW)


def test_filter_dedup_and_cap():
    articles = [
        make(title="Brand safety debate returns", link="https://x.com/1"),
        make(title="Brand safety debate returns dup", link="https://x.com/1"),  # same link -> dropped
        make(title="Retail media budget growth", link="https://x.com/2"),
        make(title="Store opens downtown", link="https://x.com/3"),  # no keyword
        make(
            title="Old brand safety piece",
            link="https://x.com/4",
            published=NOW - timedelta(hours=100),
        ),  # too old
    ]
    kept = filter_articles(articles, window_hours=30, max_articles=10, now=NOW)
    titles = [a.title for a in kept]
    assert "Brand safety debate returns" in titles
    assert "Retail media budget growth" in titles
    assert "Store opens downtown" not in titles
    assert "Old brand safety piece" not in titles
    assert len(kept) == 2


def test_filter_sorts_newest_first():
    articles = [
        make(
            title="Older viral trend",
            link="https://x.com/1",
            published=NOW - timedelta(hours=20),
        ),
        make(
            title="Newer viral trend",
            link="https://x.com/2",
            published=NOW - timedelta(hours=2),
        ),
    ]
    kept = filter_articles(articles, window_hours=30, max_articles=10, now=NOW)
    assert kept[0].title == "Newer viral trend"


def test_max_articles_cap():
    articles = [
        make(
            title=f"Trending look {i}",
            link=f"https://x.com/{i}",
            published=NOW - timedelta(minutes=i),
        )
        for i in range(10)
    ]
    kept = filter_articles(articles, window_hours=30, max_articles=3, now=NOW)
    assert len(kept) == 3
