from datetime import datetime, timezone

from fashion_trends.analyze import EditionAnalysis, Evidence, TrendDossier
from fashion_trends.config import Settings
from fashion_trends.fetch import Article
from fashion_trends.render import render_edition

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def make_dossier(**overrides):
    base = dict(
        working_name="Quiet Luxury",
        silhouette="Oversized, nieskonstruowane",
        proportions="Wydłużone",
        color="Stonowana neutralna paleta",
        material="Kaszmir, wełna",
        detail="Brak logo",
        styling="Minimalistyczne warstwowanie",
        earliest_occurrences="Sezon jesień/zima 2022 na pokazach mediolańskich",
        designers=["The Row", "Loro Piana"],
        celebrities=["Gwyneth Paltrow"],
        subcultures=["Old money"],
        platforms=["TikTok", "Instagram"],
        cultural_context="Reakcja na inflację i widoczną konsumpcję",
        stage="mainstream",
        confirming_evidence=[Evidence(text="Wzrost sprzedaży The Row", source_indices=[0])],
        contradicting_evidence="Część domów mody wraca do maksymalizmu",
        predicted_horizon="Utrzyma się przez 2-3 kolejne sezony",
        marketing_implication="Ograniczyć logotypy w nowej kolekcji",
        confidence=4,
        verified=True,
    )
    base.update(overrides)
    return TrendDossier(**base)


def test_render_edition_smoke():
    articles = [
        Article(
            title="The Row sales climb as quiet luxury holds",
            link="https://example.com/1",
            source="Vogue Business",
            summary="Sales data shows continued demand for understated luxury.",
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
    assert "Quiet Luxury" in edition.html
    assert "https://example.com/1" in edition.html
    assert "Mainstream" in edition.html
    assert "Dowody przeczące" in edition.html or "dowody przeczące" in edition.html.lower()
    # Plain-text alternative is populated.
    assert "Quiet Luxury" in edition.text
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
            source="Highsnobiety",
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
