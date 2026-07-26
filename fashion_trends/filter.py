"""Filter aggregated articles down to recent, trend-signal fashion stories."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from .fetch import Article

logger = logging.getLogger(__name__)

# Keywords that mark a story as being about an emerging/shifting fashion
# PHENOMENON rather than routine fashion-industry coverage (earnings, plain
# product drops, etc.). Matched case-insensitively with word boundaries
# against the title + summary. Keep this focused on trend-signal language so
# the newsletter stays about trend-spotting, not general fashion news.
TREND_KEYWORDS: tuple[str, ...] = (
    "trend",
    "trends",
    "trending",
    "microtrend",
    "micro-trend",
    "micro trend",
    "aesthetic",
    "revival",
    "resurgence",
    "comeback",
    "viral",
    "going viral",
    "must-have",
    "it bag",
    "it-bag",
    "it girl",
    "it-girl",
    "capsule collection",
    "street style",
    "streetwear",
    "runway",
    "catwalk",
    "collab",
    "collaboration",
    "gen z",
    "tiktok",
    "instagram",
    "y2k",
    "subculture",
    "style tribe",
    "zeitgeist",
    "cultural moment",
    "style movement",
    "quiet luxury",
    "old money",
    "core aesthetic",
    "cottagecore",
    "gorpcore",
    "balletcore",
    "normcore",
    "blokecore",
    "mob wife",
    "coastal grandma",
    "dopamine dressing",
    "silhouette",
    "resort wear",
    "maximalism",
    "minimalism",
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
