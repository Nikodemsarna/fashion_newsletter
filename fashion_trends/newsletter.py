"""End-to-end orchestration: fetch -> filter -> analyze -> render -> deliver."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analyze import EditionAnalysis, Evidence, TrendDossier, analyze
from .config import Settings
from .fetch import Article, fetch_all
from .filter import filter_articles
from .mailer import send_email
from .render import RenderedEdition, render_edition
from .sources import load_sources

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    article_count: int
    trend_count: int
    sent: bool
    skipped_reason: str | None
    edition: RenderedEdition | None


def _sample_articles(now: datetime) -> list[Article]:
    """Placeholder stories so a test edition always has content to send."""
    return [
        Article(
            title="Test edition — your Fashion Trend Watch delivery is working",
            link="https://github.com/Nikodemsarna/fashion_newsletter",
            source="Fashion Trend Watch (sample)",
            summary=(
                "This is a sample story. If you're reading it in your inbox, "
                "email delivery is configured correctly. Real editions replace "
                "this with live trend analysis."
            ),
            published=now,
        ),
        Article(
            title="Sample: quiet luxury aesthetic keeps gaining runway traction",
            link="https://github.com/Nikodemsarna/fashion_newsletter",
            source="Fashion Trend Watch (sample)",
            summary=(
                "A second sample item so you can preview the layout and "
                "trend-dossier formatting of a normal edition."
            ),
            published=now - timedelta(hours=3),
        ),
    ]


def _sample_analysis(now: datetime) -> EditionAnalysis:
    return EditionAnalysis(
        intro="To jest wydanie testowe — poniżej przykładowy fenomen trendowy.",
        trends=[
            TrendDossier(
                working_name="Sample: Quiet Luxury",
                silhouette="Przykład — dane testowe",
                proportions="Przykład — dane testowe",
                color="Przykład — dane testowe",
                material="Przykład — dane testowe",
                detail="Przykład — dane testowe",
                styling="Przykład — dane testowe",
                earliest_occurrences="Przykład — dane testowe",
                designers=["Sample Designer"],
                celebrities=["Sample Celebrity"],
                subcultures=["Sample Subculture"],
                platforms=["Sample Platform"],
                cultural_context="Przykład — dane testowe",
                stage="growth",
                confirming_evidence=[Evidence(text="Przykładowy dowód", source_indices=[0])],
                contradicting_evidence="Przykład — dane testowe",
                predicted_horizon="Przykład — dane testowe",
                marketing_implication="Przykład — dane testowe",
                confidence=3,
                verified=True,
            )
        ],
    )


def build_edition(
    settings: Settings,
    now: datetime | None = None,
    sample_if_empty: bool = False,
) -> tuple[int, int, RenderedEdition | None]:
    """Run the pipeline up to (but not including) delivery.

    When ``sample_if_empty`` is True and no live stories are found, a sample
    story + sample trend dossier are used so a (test) edition can still be
    produced.
    """
    now = now or datetime.now(timezone.utc)
    sources = load_sources(settings.feeds_path)
    logger.info("Loaded %d source feeds.", len(sources))

    raw = fetch_all(sources)
    articles = filter_articles(
        raw,
        window_hours=settings.window_hours,
        max_articles=settings.max_articles,
        now=now,
    )
    if not articles:
        if not sample_if_empty:
            return 0, 0, None
        logger.info("No live stories — using sample content for the test edition.")
        articles = _sample_articles(now)
        analysis = _sample_analysis(now)
    else:
        analysis = analyze(articles, settings)

    if not analysis.trends:
        if not sample_if_empty:
            return len(articles), 0, None
        analysis = _sample_analysis(now)

    edition = render_edition(articles, analysis, settings.template_dir, now=now)
    return len(articles), len(analysis.trends), edition


def run(
    settings: Settings,
    *,
    dry_run: bool = False,
    test_mode: bool = False,
    output_path: Path | None = None,
    now: datetime | None = None,
) -> RunResult:
    """Build and deliver today's edition.

    - ``dry_run``: render (and optionally write to ``output_path``) but do not send.
    - ``test_mode``: always send, even if there are no live trends (sample
      content is used as a fallback), and prefix the subject with ``[TEST]``.
    """
    article_count, trend_count, edition = build_edition(
        settings, now=now, sample_if_empty=test_mode
    )

    if edition is None:
        logger.info("No trend-signal stories found — skipping delivery.")
        return RunResult(article_count, 0, sent=False, skipped_reason="no_trends", edition=None)

    subject = f"[TEST] {edition.subject}" if test_mode else edition.subject

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(edition.html, encoding="utf-8")
        logger.info("Wrote rendered HTML to %s", output_path)

    if dry_run:
        logger.info("Dry run — not sending. Subject: %s", subject)
        return RunResult(
            article_count, trend_count, sent=False, skipped_reason="dry_run", edition=edition
        )

    send_email(subject, edition.html, edition.text, settings)
    return RunResult(article_count, trend_count, sent=True, skipped_reason=None, edition=edition)
