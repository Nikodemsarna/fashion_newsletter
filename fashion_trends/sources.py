"""Load the list of source portals from config/feeds.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Source:
    name: str
    url: str


def load_sources(feeds_path: Path) -> list[Source]:
    """Read the feeds config and return the list of sources.

    The file is a mapping with a top-level ``feeds`` list of ``{name, url}``.
    """
    data = yaml.safe_load(feeds_path.read_text(encoding="utf-8")) or {}
    raw_feeds = data.get("feeds", [])
    sources: list[Source] = []
    seen_urls: set[str] = set()
    for entry in raw_feeds:
        url = (entry.get("url") or "").strip()
        name = (entry.get("name") or url).strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(Source(name=name, url=url))
    return sources
