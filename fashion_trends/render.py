"""Render the edition into HTML (Jinja2) and a plain-text alternative."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .analyze import STAGE_LABELS_PL, EditionAnalysis, TrendDossier
from .fetch import Article

STAGE_COLORS = {
    "signal": "#8a91a3",
    "emerging": "#1f6feb",
    "growth": "#0f9d58",
    "mainstream": "#7c3aed",
    "saturation": "#b7791f",
    "decline": "#c0392b",
}


@dataclass
class RenderedEvidence:
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (label, url)


@dataclass
class RenderedTrend:
    working_name: str
    silhouette: str
    proportions: str
    color: str
    material: str
    detail: str
    styling: str
    earliest_occurrences: str
    designers: list[str]
    celebrities: list[str]
    subcultures: list[str]
    platforms: list[str]
    cultural_context: str
    stage: str
    stage_label: str
    stage_color: str
    confirming_evidence: list[RenderedEvidence]
    contradicting_evidence: str
    predicted_horizon: str
    marketing_implication: str
    confidence: int
    confidence_dots: str
    verified: bool
    primary_link: str


@dataclass
class RenderedEdition:
    subject: str
    date_label: str
    intro: str
    trends: list[RenderedTrend]
    count: int
    html: str
    text: str


def _confidence_dots(confidence: int) -> str:
    return "●" * confidence + "○" * (5 - confidence)


def _to_rendered_trend(dossier: TrendDossier, articles: list[Article]) -> RenderedTrend:
    evidence = []
    primary_link = ""
    for ev in dossier.confirming_evidence:
        links = []
        for idx in ev.source_indices:
            art = articles[idx]
            links.append((art.source, art.link))
            if not primary_link:
                primary_link = art.link
        evidence.append(RenderedEvidence(text=ev.text, links=links))

    if not primary_link and articles:
        # Fall back to any article referenced anywhere in this dossier's evidence.
        for ev in dossier.confirming_evidence:
            if ev.source_indices:
                primary_link = articles[ev.source_indices[0]].link
                break

    return RenderedTrend(
        working_name=dossier.working_name,
        silhouette=dossier.silhouette,
        proportions=dossier.proportions,
        color=dossier.color,
        material=dossier.material,
        detail=dossier.detail,
        styling=dossier.styling,
        earliest_occurrences=dossier.earliest_occurrences,
        designers=dossier.designers,
        celebrities=dossier.celebrities,
        subcultures=dossier.subcultures,
        platforms=dossier.platforms,
        cultural_context=dossier.cultural_context,
        stage=dossier.stage,
        stage_label=STAGE_LABELS_PL.get(dossier.stage, dossier.stage),
        stage_color=STAGE_COLORS.get(dossier.stage, "#8a91a3"),
        confirming_evidence=evidence,
        contradicting_evidence=dossier.contradicting_evidence,
        predicted_horizon=dossier.predicted_horizon,
        marketing_implication=dossier.marketing_implication,
        confidence=dossier.confidence,
        confidence_dots=_confidence_dots(dossier.confidence),
        verified=dossier.verified,
        primary_link=primary_link,
    )


def render_edition(
    articles: list[Article],
    analysis: EditionAnalysis,
    template_dir: Path,
    now: datetime | None = None,
) -> RenderedEdition:
    now = now or datetime.now(timezone.utc)
    today: date = now.date()
    date_label = today.strftime("%A, %d %B %Y")
    count = len(analysis.trends)
    subject = f"Fashion Trend Watch — {today.isoformat()}: {count} " + (
        "zjawisko" if count == 1 else "zjawisk trendowych"
    )

    trends = [_to_rendered_trend(t, articles) for t in analysis.trends]

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email.html.j2")
    html = template.render(
        date_label=date_label,
        intro=analysis.intro,
        trends=trends,
        count=count,
    )
    text = _render_text(date_label, analysis.intro, trends)

    return RenderedEdition(
        subject=subject,
        date_label=date_label,
        intro=analysis.intro,
        trends=trends,
        count=count,
        html=html,
        text=text,
    )


def _render_text(date_label: str, intro: str, trends: list[RenderedTrend]) -> str:
    lines = ["FASHION TREND WATCH", date_label, "=" * 40, ""]
    if intro:
        lines += [intro, ""]

    for t in trends:
        lines.append(f"# {t.working_name}  [{t.stage_label} · pewność {t.confidence}/5]")
        lines.append("-" * 40)
        lines.append(
            f"Cechy: sylwetka: {t.silhouette}; proporcje: {t.proportions}; "
            f"kolor: {t.color}; materiał: {t.material}; detal: {t.detail}; "
            f"stylizacja: {t.styling}"
        )
        lines.append(f"Najwcześniejsze wystąpienia: {t.earliest_occurrences}")
        signal = []
        if t.designers:
            signal.append("projektanci: " + ", ".join(t.designers))
        if t.celebrities:
            signal.append("celebryci: " + ", ".join(t.celebrities))
        if t.subcultures:
            signal.append("subkultury: " + ", ".join(t.subcultures))
        if t.platforms:
            signal.append("platformy: " + ", ".join(t.platforms))
        if signal:
            lines.append("Nośniki sygnału: " + "; ".join(signal))
        lines.append(f"Kontekst: {t.cultural_context}")
        lines.append("Dowody potwierdzające:")
        for ev in t.confirming_evidence:
            lines.append(f"  • {ev.text}")
            for label, url in ev.links:
                lines.append(f"    - {label}: {url}")
        lines.append(f"Dowody przeczące: {t.contradicting_evidence}")
        lines.append(f"Przewidywany horyzont: {t.predicted_horizon}")
        lines.append(f"Konsekwencja marketingowa: {t.marketing_implication}")
        if not t.verified:
            lines.append("(!) NIEZWERYFIKOWANE — brak klucza API dla analizy LLM")
        lines.append("")

    lines.append("—")
    lines.append("Fashion Trend Watch · codzienny przegląd zjawisk trendowych w modzie")
    return "\n".join(lines)
