"""Fetch and parse RSS/Atom feeds into a normalized Article model."""

from __future__ import annotations

import calendar
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import requests

from .sources import Source

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; FashionTrendWatchBot/1.0; "
    "+https://github.com/Nikodemsarna/fashion_newsletter)"
)
REQUEST_TIMEOUT = 20  # seconds
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Article:
    title: str
    link: str
    source: str
    summary: str
    published: datetime | None

    @property
    def dedup_key(self) -> str:
        """Stable identity for de-duplication (prefer link, fall back to title)."""
        if self.link:
            return self.link.split("?")[0].rstrip("/").lower()
        return _normalize_title(self.title)


def _normalize_title(title: str) -> str:
    return _WS_RE.sub(" ", title or "").strip().lower()


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace from a feed summary."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("&nbsp;", " ")
    )
    return _WS_RE.sub(" ", text).strip()


def _parse_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def _fetch_one(source: Source) -> list[Article]:
    try:
        resp = requests.get(
            source.url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s (%s): %s", source.name, source.url, exc)
        return []

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Could not parse feed for %s: %s", source.name, parsed.get("bozo_exception")
        )
        return []

    articles: list[Article] = []
    for entry in parsed.entries:
        title = _clean(entry.get("title", ""))
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = _clean(entry.get("summary", entry.get("description", "")))
        articles.append(
            Article(
                title=title,
                link=link,
                source=source.name,
                summary=summary,
                published=_parse_published(entry),
            )
        )
    logger.info("Fetched %d entries from %s", len(articles), source.name)
    return articles


def fetch_all(sources: list[Source], max_workers: int = 8) -> list[Article]:
    """Fetch every source concurrently and return the combined article list."""
    articles: list[Article] = []
    if not sources:
        return articles
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, src): src for src in sources}
        for future in as_completed(futures):
            try:
                articles.extend(future.result())
            except Exception as exc:  # defensive: a single feed must not abort the run
                src = futures[future]
                logger.warning("Unexpected error fetching %s: %s", src.name, exc)
    logger.info("Fetched %d total entries from %d sources", len(articles), len(sources))
    return articles
