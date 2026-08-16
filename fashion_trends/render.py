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
    mechanic: str
    channel: str
    tone: str
    target_audience: str
    creative_hook: str
    measurement_signal: str
    earliest_occurrences: str
    brands: list[str]
    agencies: list[str]
    voices: list[str]
    platforms: list[str]
    cultural_context: str
    stage: str
    stage_label: str
    stage_color: str
    confirming_evidence: list[RenderedEvidence]
    contradicting_evidence: str
    predicted_horizon: str
    business_implication: str
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
        mechanic=dossier.mechanic,
        channel=dossier.channel,
        tone=dossier.tone,
        target_audience=dossier.target_audience,
        creative_hook=dossier.creative_hook,
        measurement_signal=dossier.measurement_signal,
        earliest_occurrences=dossier.earliest_occurrences,
        brands=dossier.brands,
        agencies=dossier.agencies,
        voices=dossier.voices,
        platforms=dossier.platforms,
        cultural_context=dossier.cultural_context,
        stage=dossier.stage,
        stage_label=STAGE_LABELS_PL.get(dossier.stage, dossier.stage),
        stage_color=STAGE_COLORS.get(dossier.stage, "#8a91a3"),
        confirming_evidence=evidence,
        contradicting_evidence=dossier.contradicting_evidence,
        predicted_horizon=dossier.predicted_horizon,
        business_implication=dossier.business_implication,
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
    subject = f"Marketing Signals — {today.isoformat()}: {count} " + (
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
    lines = ["MARKETING SIGNALS", date_label, "=" * 40, ""]
    if intro:
        lines += [intro, ""]

    for t in trends:
        lines.append(f"# {t.working_name}  [{t.stage_label} · pewność {t.confidence}/5]")
        lines.append("-" * 40)
        lines.append(
            f"Cechy: mechanika: {t.mechanic}; kanał: {t.channel}; "
            f"ton: {t.tone}; grupa docelowa: {t.target_audience}; "
            f"insight: {t.creative_hook}; mierzalność: {t.measurement_signal}"
        )
        lines.append(f"Najwcześniejsze wystąpienia: {t.earliest_occurrences}")
        signal = []
        if t.brands:
            signal.append("marki: " + ", ".join(t.brands))
        if t.agencies:
            signal.append("agencje: " + ", ".join(t.agencies))
        if t.voices:
            signal.append("głosy branżowe: " + ", ".join(t.voices))
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
        lines.append(f"Konsekwencja biznesowa: {t.business_implication}")
        if not t.verified:
            lines.append("(!) NIEZWERYFIKOWANE — brak klucza API dla analizy LLM")
        lines.append("")

    lines.append("—")
    lines.append("Marketing Signals · codzienny przegląd zjawisk trendowych w marketingu")
    return "\n".join(lines)
