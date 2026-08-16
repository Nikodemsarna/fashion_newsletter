"""Filter aggregated articles down to recent, trend-signal marketing stories."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from .fetch import Article

logger = logging.getLogger(__name__)

# Keywords that mark a story as being about an emerging/shifting marketing
# PHENOMENON rather than routine industry coverage (earnings, plain personnel
# moves, etc.). Matched case-insensitively with word boundaries against the
# title + summary. Keep this focused on trend-signal language so the
# newsletter stays about trend-spotting, not general marketing news.
TREND_KEYWORDS: tuple[str, ...] = (
    "trend",
    "trends",
    "trending",
    "microtrend",
    "micro-trend",
    "micro trend",
    "campaign",
    "rebrand",
    "rebranding",
    "backlash",
    "controversy",
    "viral",
    "going viral",
    "brand safety",
    "de-influencing",
    "deinfluencing",
    "retail media",
    "creator economy",
    "creator-led",
    "influencer marketing",
    "greenwashing",
    "brand activism",
    "purpose-driven",
    "attention economy",
    "dark social",
    "zero-party data",
    "first-party data",
    "cookieless",
    "privacy-first",
    "owned media",
    "generative ai",
    "ai-generated",
    "ai advertising",
    "gen z",
    "tiktok",
    "short-form video",
    "user-generated content",
    "ugc",
    "b2b marketing",
    "nostalgia marketing",
    "meme marketing",
    "guerrilla marketing",
    "nation branding",
    "soft power",
    "zeitgeist",
    "cultural moment",
    "cannes lions",
    "award-winning campaign",
    "case study",
    "effectiveness",
)

_KEYWORD_RE = re.compile(
    r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(k) for k in TREND_KEYWORDS),
    re.IGNORECASE,
)


def matches_trend_signal(article: Article) -> bool:
    haystack = f"{article.title}\n{article.summary}"
    return bool(_KEYWORD_RE.search(haystack))


def is_recent(article: Article, window: timedelta, now: datetime | None = None) -> bool:
    """Recent if published within the window. Undated entries are kept."""
    if article.published is None:
        return True
    now = now or datetime.now(timezone.utc)
    return article.published >= (now - window)


def filter_articles(
    articles: list[Article],
    window_hours: int,
    max_articles: int,
    now: datetime | None = None,
) -> list[Article]:
    """Apply recency + keyword filters, de-duplicate, sort, and cap the list."""
    now = now or datetime.now(timezone.utc)
    window = timedelta(hours=window_hours)

    seen: set[str] = set()
    kept: list[Article] = []
    for article in articles:
        if not matches_trend_signal(article):
            continue
        if not is_recent(article, window, now=now):
            continue
        key = article.dedup_key
        if key in seen:
            continue
        seen.add(key)
        kept.append(article)

    # Newest first; undated entries sink to the bottom.
    kept.sort(
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    logger.info(
        "Filtered %d trend-signal stories from %d entries (window=%dh)",
        len(kept),
        len(articles),
        window_hours,
    )
    return kept[:max_articles]
