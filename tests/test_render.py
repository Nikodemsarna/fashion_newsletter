from datetime import datetime, timezone

from fashion_trends.analyze import EditionAnalysis, Evidence, TrendDossier
from fashion_trends.config import Settings
from fashion_trends.fetch import Article
from fashion_trends.render import render_edition

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def make_dossier(**overrides):
    base = dict(
        working_name="Retail Media",
        mechanic="Reklama celowana na danych transakcyjnych",
        channel="Retail media network",
        tone="Rzeczowy, wynikowy",
        target_audience="Kupujący w sieciach handlowych",
        creative_hook="Dane o realnych zakupach ponad deklaracjami",
        measurement_signal="Wzrost wydatków na retail media r/r",
        earliest_occurrences="Pierwsze sieci uruchamiają jednostki reklamowe w 2023",
        brands=["Duża sieć handlowa", "Marka FMCG"],
        agencies=["Wyspecjalizowany dom mediowy"],
        voices=["Analityk eMarketer"],
        platforms=["Retail media network", "Programmatic"],
        cultural_context="Presja na mierzalny zwrot z wydatków reklamowych",
        stage="mainstream",
        confirming_evidence=[Evidence(text="Wzrost wydatków na retail media", source_indices=[0])],
        contradicting_evidence="Fragmentacja narzędzi pomiarowych między sieciami",
        predicted_horizon="Utrzyma się przez kolejne 2-3 lata",
        business_implication="Budować kompetencje analityczne wewnątrz zespołu marketingu",
        confidence=4,
        verified=True,
    )
    base.update(overrides)
    return TrendDossier(**base)


def test_render_edition_smoke():
    articles = [
        Article(
            title="Retail media budgets climb as networks scale",
            link="https://example.com/1",
            source="Marketing Week",
            summary="Spend data shows continued demand for retail media.",
            published=NOW,
        ),
    ]
    analysis = EditionAnalysis(
        intro="Jedno kluczowe zjawisko trendowe dzisiaj.",
        trends=[make_dossier()],
    )
    settings = Settings()
    edition = render_edition(articles, analysis, settings.template_dir, now=NOW)

    assert edition.count == 1
    assert "2026-06-30" in edition.subject
    assert len(edition.trends) == 1
    assert "Retail Media" in edition.html
    assert "https://example.com/1" in edition.html
    assert "Mainstream" in edition.html
    assert "Dowody przeczące" in edition.html or "dowody przeczące" in edition.html.lower()
    # Plain-text alternative is populated.
    assert "Retail Media" in edition.text
    assert "Dowody potwierdzające" in edition.text


def test_render_handles_no_trends():
    settings = Settings()
    analysis = EditionAnalysis(intro="", trends=[])
    edition = render_edition([], analysis, settings.template_dir, now=NOW)
    assert edition.count == 0
    assert len(edition.trends) == 0


def test_render_marks_unverified_dossier():
    articles = [
        Article(
            title="Some trend-adjacent story",
            link="https://example.com/2",
            source="Digiday",
            summary="",
            published=NOW,
        ),
    ]
    analysis = EditionAnalysis(
        intro="",
        trends=[make_dossier(verified=False, confidence=1)],
    )
    settings = Settings()
    edition = render_edition(articles, analysis, settings.template_dir, now=NOW)
    assert "NIEZWERYFIKOWANE" in edition.html
