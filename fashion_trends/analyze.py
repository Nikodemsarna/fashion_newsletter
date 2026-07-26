"""Identify fashion-trend phenomena and build a verification dossier for each.

Unlike a plain "summarize this article" pass, this stage asks the LLM to look
across the day's filtered fashion-press stories, cluster them into distinct
trend PHENOMENA (a trend rarely lives in a single article), and for each one
answer a fixed set of trend-verification criteria:

  1. working_name           - nazwa robocza zjawiska
  2. features                - widoczne cechy: sylwetka, proporcje, kolor,
                                materiał, detal, sposób stylizacji
  3. earliest_occurrences    - najwcześniejsze znane wystąpienia
  4. signal_carriers         - projektanci, celebryci, subkultury, platformy
  5. cultural_context        - kontekst kulturowy/polityczny/ekonomiczny
  6. stage                   - sygnał -> wschodzący -> wzrost -> mainstream
                                -> nasycenie -> schyłek
  7. confirming_evidence     - dowody potwierdzające (linked back to articles)
  8. contradicting_evidence  - dowody przeczące
  9. predicted_horizon       - przewidywany horyzont
  10. marketing_implication  - możliwa konsekwencja marketingowa
  11. confidence             - poziom pewności 1-5

Supported providers (auto-detected from whichever API key is set, or forced
via ``FASHION_PROVIDER``): gemini, groq, anthropic. Without any key, a
lightweight, explicitly-unverified fallback grouping is produced instead.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import requests

from .config import Settings
from .fetch import Article

logger = logging.getLogger(__name__)

_TIMEOUT = 120
_MAX_TOKENS = 16000

STAGES: tuple[str, ...] = (
    "signal",
    "emerging",
    "growth",
    "mainstream",
    "saturation",
    "decline",
)

STAGE_LABELS_PL = {
    "signal": "Sygnał",
    "emerging": "Trend wschodzący",
    "growth": "Wzrost",
    "mainstream": "Mainstream",
    "saturation": "Nasycenie",
    "decline": "Schyłek",
}

_SYSTEM_PROMPT = (
    "Jesteś starszym analitykiem trendów w modzie i krytykiem kultury wizualnej, "
    "piszącym wewnętrzny newsletter trend-spotting dla profesjonalnego odbiorcy "
    "(dział projektowy/marketingowy marki modowej). Twoim zadaniem NIE jest "
    "streszczanie artykułów, tylko wykrywanie leżących pod nimi ZJAWISK "
    "(fenomenów trendowych) i rygorystyczna weryfikacja każdego z nich według "
    "stałego zestawu kryteriów.\n\n"
    "Zasady pracy:\n"
    "- Jeden trend rzadko mieści się w jednym artykule — łącz powiązane "
    "historie w jedno zjawisko i pomijaj artykuły, które nie wskazują na żaden "
    "odrębny trend (np. czysto biznesowe newsy bez sygnału stylistycznego).\n"
    "- Możesz i powinieneś korzystać z własnej wiedzy o historii mody, popkulturze "
    "i mediach społecznościowych, aby uzupełnić kryteria, których dostarczone "
    "artykuły nie pokrywają wprost (np. najwcześniejsze wystąpienia, kontekst "
    "kulturowy) — ale nigdy nie zmyślaj fałszywej precyzji (dokładnych dat, "
    "nazwisk, liczb), której nie jesteś pewien. Jeśli nie masz pewności, podaj "
    "najlepsze przybliżenie i obniż poziom pewności zamiast fabrykować szczegóły.\n"
    "- 'Dowody potwierdzające' muszą realnie wspierać istnienie i etap rozwoju "
    "trendu; jeśli powołujesz się na dostarczony artykuł, podaj jego indeks w "
    "source_indices. Możesz też podać dowód spoza dostarczonych artykułów "
    "(source_indices: []), jeśli to wiedza ogólna.\n"
    "- 'Dowody przeczące' są obowiązkowym polem krytycznym — aktywnie szukaj "
    "kontrargumentów (np. trend ograniczony do jednej bańki na TikToku, brak "
    "przełożenia na sprzedaż, sprzeczne sygnały od innych domów mody, oznaki "
    "przesytu). Napisz 'brak istotnych dowodów przeczących' tylko jeśli "
    "naprawdę ich nie znajdujesz.\n"
    "- Poziom pewności (1-5) odzwierciedla siłę i niezależność dowodów: "
    "5 = potwierdzone wieloma niezależnymi, mocnymi sygnałami; "
    "1 = spekulacyjne, pojedynczy słaby sygnał.\n"
    "- Pisz zwięźle, rzeczowo, bez marketingowego zadęcia, po polsku."
)

_JSON_SHAPE = (
    "Odpowiedz WYŁĄCZNIE jednym obiektem JSON, bez markdown, dokładnie w tym "
    "kształcie:\n"
    "{\n"
    '  "intro": "2-4 zdania wprowadzenia redakcyjnego o dzisiejszym wydaniu",\n'
    '  "trends": [\n'
    "    {\n"
    '      "working_name": "nazwa robocza zjawiska",\n'
    '      "silhouette": "sylwetka",\n'
    '      "proportions": "proporcje",\n'
    '      "color": "kolor",\n'
    '      "material": "materiał",\n'
    '      "detail": "detal",\n'
    '      "styling": "sposób stylizacji",\n'
    '      "earliest_occurrences": "najwcześniejsze znane wystąpienia",\n'
    '      "designers": ["projektanci/marki niosące sygnał"],\n'
    '      "celebrities": ["celebryci/influencerzy niosący sygnał"],\n'
    '      "subcultures": ["subkultury/społeczności niosące sygnał"],\n'
    '      "platforms": ["platformy niosące sygnał, np. TikTok, Instagram, Depop"],\n'
    '      "cultural_context": "kontekst kulturowy, polityczny lub ekonomiczny",\n'
    '      "stage": "signal|emerging|growth|mainstream|saturation|decline",\n'
    '      "confirming_evidence": [{"text": "dowód potwierdzający", '
    '"source_indices": [<int z listy ARTYKUŁY>]}],\n'
    '      "contradicting_evidence": "dowody przeczące (obowiązkowe)",\n'
    '      "predicted_horizon": "przewidywany horyzont czasowy",\n'
    '      "marketing_implication": "możliwa konsekwencja marketingowa",\n'
    '      "confidence": <int 1-5>\n'
    "    }\n"
    "  ]\n"
    "}\n"
)

# JSON schema reused by providers that support structured output (Anthropic).
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "trends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "working_name": {"type": "string"},
                    "silhouette": {"type": "string"},
                    "proportions": {"type": "string"},
                    "color": {"type": "string"},
                    "material": {"type": "string"},
                    "detail": {"type": "string"},
                    "styling": {"type": "string"},
                    "earliest_occurrences": {"type": "string"},
                    "designers": {"type": "array", "items": {"type": "string"}},
                    "celebrities": {"type": "array", "items": {"type": "string"}},
                    "subcultures": {"type": "array", "items": {"type": "string"}},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "cultural_context": {"type": "string"},
                    "stage": {"type": "string", "enum": list(STAGES)},
                    "confirming_evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "source_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                },
                            },
                            "required": ["text", "source_indices"],
                            "additionalProperties": False,
                        },
                    },
                    "contradicting_evidence": {"type": "string"},
                    "predicted_horizon": {"type": "string"},
                    "marketing_implication": {"type": "string"},
                    "confidence": {"type": "integer"},
                },
                "required": [
                    "working_name",
                    "silhouette",
                    "proportions",
                    "color",
                    "material",
                    "detail",
                    "styling",
                    "earliest_occurrences",
                    "designers",
                    "celebrities",
                    "subcultures",
                    "platforms",
                    "cultural_context",
                    "stage",
                    "confirming_evidence",
                    "contradicting_evidence",
                    "predicted_horizon",
                    "marketing_implication",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intro", "trends"],
    "additionalProperties": False,
}


@dataclass
class Evidence:
    text: str
    source_indices: list[int] = field(default_factory=list)


@dataclass
class TrendDossier:
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
    confirming_evidence: list[Evidence]
    contradicting_evidence: str
    predicted_horizon: str
    marketing_implication: str
    confidence: int
    verified: bool = True  # False for the no-LLM-key fallback


@dataclass
class EditionAnalysis:
    intro: str
    trends: list[TrendDossier]


def _build_user_prompt(articles: list[Article]) -> str:
    lines = [
        "Poniżej znajduje się dzisiejsza pula artykułów prasy modowej (po "
        "filtrze sygnałów trendowych). Zidentyfikuj do 8 odrębnych zjawisk "
        "trendowych i zweryfikuj każde zgodnie z podanym schematem.",
        "",
        _JSON_SHAPE,
        "",
        "ARTYKUŁY:",
        "",
    ]
    for i, art in enumerate(articles):
        desc = art.summary or "(brak opisu)"
        published = art.published.isoformat() if art.published else "brak daty"
        lines.append(f"[{i}] Źródło: {art.source} | Data: {published}")
        lines.append(f"    Tytuł: {art.title}")
        lines.append(f"    Opis: {desc}")
        lines.append("")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences/prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _clean_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _payload_to_analysis(data: dict, n_articles: int, max_trends: int) -> EditionAnalysis:
    trends: list[TrendDossier] = []
    for item in data.get("trends", [])[:max_trends]:
        if not isinstance(item, dict):
            continue
        working_name = str(item.get("working_name") or "").strip()
        if not working_name:
            continue

        stage = str(item.get("stage") or "signal").strip().lower()
        if stage not in STAGES:
            stage = "signal"

        evidence: list[Evidence] = []
        for ev in item.get("confirming_evidence", []) or []:
            if not isinstance(ev, dict):
                continue
            text = str(ev.get("text") or "").strip()
            if not text:
                continue
            indices = [
                idx
                for idx in (ev.get("source_indices") or [])
                if isinstance(idx, int) and 0 <= idx < n_articles
            ]
            evidence.append(Evidence(text=text, source_indices=indices))

        try:
            confidence = int(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = 3
        confidence = max(1, min(5, confidence))

        trends.append(
            TrendDossier(
                working_name=working_name,
                silhouette=str(item.get("silhouette") or "").strip(),
                proportions=str(item.get("proportions") or "").strip(),
                color=str(item.get("color") or "").strip(),
                material=str(item.get("material") or "").strip(),
                detail=str(item.get("detail") or "").strip(),
                styling=str(item.get("styling") or "").strip(),
                earliest_occurrences=str(item.get("earliest_occurrences") or "").strip(),
                designers=_clean_str_list(item.get("designers")),
                celebrities=_clean_str_list(item.get("celebrities")),
                subcultures=_clean_str_list(item.get("subcultures")),
                platforms=_clean_str_list(item.get("platforms")),
                cultural_context=str(item.get("cultural_context") or "").strip(),
                stage=stage,
                confirming_evidence=evidence,
                contradicting_evidence=str(item.get("contradicting_evidence") or "").strip(),
                predicted_horizon=str(item.get("predicted_horizon") or "").strip(),
                marketing_implication=str(item.get("marketing_implication") or "").strip(),
                confidence=confidence,
                verified=True,
            )
        )

    return EditionAnalysis(intro=(data.get("intro") or "").strip(), trends=trends)


_NAMED_AESTHETICS: tuple[str, ...] = (
    "cottagecore",
    "gorpcore",
    "balletcore",
    "normcore",
    "blokecore",
    "mob wife",
    "coastal grandma",
    "quiet luxury",
    "old money",
    "y2k",
    "dopamine dressing",
)


def _fallback_analysis(articles: list[Article]) -> EditionAnalysis:
    """No LLM key: group by named aesthetic keyword, explicitly unverified.

    This skips the actual criteria (silhouette, cultural context, etc.) since
    those require real analysis. Each group is clearly marked as an
    unverified raw-signal cluster, not a full trend dossier.
    """
    groups: dict[str, list[int]] = {}
    other: list[int] = []
    for i, art in enumerate(articles):
        haystack = f"{art.title}\n{art.summary}".lower()
        matched = next((name for name in _NAMED_AESTHETICS if name in haystack), None)
        if matched:
            groups.setdefault(matched, []).append(i)
        else:
            other.append(i)

    trends: list[TrendDossier] = []
    for name, idxs in groups.items():
        trends.append(_unverified_dossier(name.title(), idxs, articles))
    if other:
        trends.append(_unverified_dossier("Niesklasyfikowane sygnały trendowe", other, articles))

    intro = (
        f"Brak skonfigurowanego klucza LLM (GEMINI_API_KEY / GROQ_API_KEY / "
        f"ANTHROPIC_API_KEY) — poniżej surowe pogrupowanie {len(articles)} "
        "artykułów sygnałowych, BEZ pełnej weryfikacji kryteriów trendu."
    )
    return EditionAnalysis(intro=intro, trends=trends)


def _unverified_dossier(name: str, idxs: list[int], articles: list[Article]) -> TrendDossier:
    note = "brak analizy LLM — skonfiguruj klucz API, aby uzyskać pełną weryfikację"
    return TrendDossier(
        working_name=name,
        silhouette=note,
        proportions=note,
        color=note,
        material=note,
        detail=note,
        styling=note,
        earliest_occurrences=note,
        designers=[],
        celebrities=[],
        subcultures=[],
        platforms=[a.source for a in articles],
        cultural_context=note,
        stage="signal",
        confirming_evidence=[
            Evidence(text=articles[i].title, source_indices=[i]) for i in idxs
        ],
        contradicting_evidence=note,
        predicted_horizon=note,
        marketing_implication=note,
        confidence=1,
        verified=False,
    )


def analyze(articles: list[Article], settings: Settings) -> EditionAnalysis:
    """Produce an EditionAnalysis using the configured provider."""
    if not articles:
        return EditionAnalysis(intro="", trends=[])

    if not settings.has_analyzer:
        logger.warning(
            "No LLM API key set — using unverified raw-signal grouping fallback."
        )
        return _fallback_analysis(articles)

    prompt = _build_user_prompt(articles)
    try:
        if settings.provider == "gemini":
            data = _call_gemini(prompt, settings)
        elif settings.provider == "groq":
            data = _call_groq(prompt, settings)
        elif settings.provider == "anthropic":
            data = _call_anthropic(prompt, settings)
        else:  # pragma: no cover - guarded by has_analyzer
            return _fallback_analysis(articles)
    except Exception as exc:
        logger.error(
            "Trend analysis via %s failed (%s) — falling back.", settings.provider, exc
        )
        return _fallback_analysis(articles)

    analysis = _payload_to_analysis(data, len(articles), settings.max_trends)
    logger.info(
        "Identified %d trend dossiers from %d articles with %s (%s).",
        len(analysis.trends),
        len(articles),
        settings.provider,
        settings.resolved_model,
    )
    return analysis


# --- Providers --------------------------------------------------------------


def _call_gemini(prompt: str, settings: Settings) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.resolved_model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
            "maxOutputTokens": _MAX_TOKENS,
        },
    }
    resp = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json=body,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)


def _call_groq(prompt: str, settings: Settings) -> dict:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json={
            "model": settings.resolved_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": _MAX_TOKENS,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(text)


def _call_anthropic(prompt: str, settings: Settings) -> dict:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'anthropic' package is required for the Anthropic provider "
            "(pip install anthropic)."
        ) from exc

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.resolved_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        output_config={
            "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
            "effort": settings.effort,
        },
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _extract_json(text)
