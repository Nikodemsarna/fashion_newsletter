# 📡 Marketing Signals

A daily email newsletter that aggregates news from across the marketing and
advertising trade press, filters it down to **trend-signal stories**
(campaigns, platform shifts, brand-strategy moves, market data, critical
voices), and uses an LLM to identify the distinct trend **phenomena** behind
them — then builds a verification dossier for each one before emailing a
clean digest.

Built to run unattended on **GitHub Actions** — one scheduled job per day.
Same pipeline shape as its sibling project,
[Small-Sat News](https://github.com/Nikodemsarna/Small-Sat-news), adapted for
marketing-trend verification instead of article summarization.

---

## How it works

```
config/feeds.yaml          (marketing-trade portals with an RSS feed)
        │
        ▼
 fetch    → pulls & parses all feeds concurrently (resilient to dead feeds)
        ▼
 filter   → keeps only recent trend-signal stories, de-duplicates
        ▼
 analyze  → one batched LLM call: clusters stories into distinct trend
            phenomena and builds a full verification dossier for each
            (Gemini/Groq free tiers, or Claude; unverified fallback if no key)
        ▼
 render   → responsive HTML email + plain-text alternative (Jinja2)
        ▼
 deliver  → Resend API or SMTP, to your inbox
```

Each stage is a small module under
[`fashion_trends/`](fashion_trends/). A single edition is one LLM call per
day, so running costs are negligible.

### The verification dossier

Unlike a plain news digest, this newsletter does not summarize articles one
by one — it asks the LLM to spot the trend **phenomenon** underlying a
cluster of related stories (plus its own broader marketing-history knowledge)
and verify it against a fixed 11-point checklist, for every trend in every
edition:

1. **Nazwa robocza zjawiska** — working name of the phenomenon
2. **Widoczne cechy** — mechanika/format, kanał, ton, grupa docelowa, insight
   kreatywny, sygnał mierzalności
3. **Najwcześniejsze znane wystąpienia**
4. **Nośniki sygnału** — marki, agencje, głosy branżowe, platformy
5. **Kontekst kulturowy, polityczny lub ekonomiczny**
6. **Etap rozwoju** — sygnał → trend wschodzący → wzrost → mainstream →
   nasycenie → schyłek
7. **Dowody potwierdzające** — linked back to the source articles where
   applicable
8. **Dowody przeczące** — a mandatory, actively-sought counter-argument field
9. **Przewidywany horyzont**
10. **Możliwa konsekwencja biznesowa**
11. **Poziom pewności (1–5)**

If no LLM key is configured, the newsletter still sends but is explicit about
it: stories are grouped by a known phenomenon keyword only, every dossier
field is marked as unverified, and confidence is pinned to 1/5.

---

## Quick start (local)

```bash
pip install -r requirements.txt

# Preview today's edition without sending — writes the HTML so you can open it.
python -m fashion_trends --dry-run --output output/edition.html
open output/edition.html        # or just inspect the file
```

`--dry-run` needs no API key (it falls back to the unverified grouping and
never sends). Add a **free** `GEMINI_API_KEY` for real trend verification.

To actually send, configure a delivery provider (below) and drop `--dry-run`.

---

## Configuration

All configuration is via environment variables — see
[`.env.example`](.env.example) for the full list. The important ones:

| Variable | Purpose | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Google Gemini key (free) for trend analysis | _(falls back to unverified grouping)_ |
| `GROQ_API_KEY` | Groq key (free) — alternative analyzer | — |
| `ANTHROPIC_API_KEY` | Claude key (paid) — alternative analyzer | — |
| `FASHION_PROVIDER` | Force `gemini` / `groq` / `anthropic` | _(auto-detected)_ |
| `NEWSLETTER_TO` | Recipient address | `nikodem.sarna@gmail.com` |
| `RESEND_API_KEY` | Use Resend for delivery | — |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Use SMTP for delivery | — |
| `NEWSLETTER_FROM` | From address | `Marketing Signals <onboarding@resend.dev>` |
| `FASHION_MODEL` | Override model | _(provider default)_ |
| `FASHION_EFFORT` | Anthropic reasoning effort | `high` |
| `FASHION_WINDOW_HOURS` | How far back "recent" reaches | `72` |
| `FASHION_MAX_ARTICLES` | Cap on articles fed into analysis | `60` |
| `FASHION_MAX_TRENDS` | Cap on trend dossiers per edition | `8` |

### Analysis: pick a provider (free options)

The primary provider is auto-detected from whichever key you set:

- **Google Gemini** (recommended, free): grab a key — no credit card — at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and set
  `GEMINI_API_KEY`. Default model `gemini-flash-latest` — a Google-maintained
  alias, not a pinned dot-release. A pinned release was tried here briefly
  and started 404ing within a day (Google's model lineup moves faster than
  this file gets updated by hand, and an invalid pin fails *every* call,
  forever, until someone notices and fixes the name). The alias avoids that
  failure mode entirely; its own failure mode — brief overload right after
  Google repoints it at a new model — is transient and exactly what the
  retry + cross-provider failover below are for.
- **Groq** (free, fast): key at [console.groq.com/keys](https://console.groq.com/keys),
  set `GROQ_API_KEY`. Default model `llama-3.3-70b-versatile`.
- **Anthropic / Claude** (paid): set `ANTHROPIC_API_KEY` and
  `pip install anthropic`. Default model `claude-opus-4-8`.

**Set more than one key and you get automatic failover**: if the primary
provider exhausts its retries (see below), the next provider with a
configured key is tried before the edition degrades to the unverified
fallback. This is what actually protects against a days-long single-provider
outage — per-provider retries alone can't, and neither can picking "the
right" model name, since any name can start 404ing without warning.
**Recommended: set both `GEMINI_API_KEY` and `GROQ_API_KEY` (both free)** —
with only one key configured, a bad day for that one provider means every
edition is unverified until it recovers. Failover is skipped if
`FASHION_MODEL` forces a specific model, since that model name may not exist
on the fallback provider.

Each provider call also retries transient failures (`503`, `429`, timeouts)
up to 3 times with a short delay before moving to the next provider or, if
none are left, to the unverified fallback.

Gemini and Groq run over plain HTTP — no extra Python dependency. With no key
at all, the edition still sends but every dossier is marked unverified.

### Delivery: pick one provider

- **Resend** (recommended — one key, no SMTP setup): create a key at
  [resend.com](https://resend.com) and set `RESEND_API_KEY`. The free tier sends
  from `onboarding@resend.dev` to any address; verify a domain to use your own
  `From`.
- **SMTP** (e.g. Gmail): create an [App Password](https://support.google.com/accounts/answer/185833)
  and set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`.

If `RESEND_API_KEY` is set it is used; otherwise SMTP is used if `SMTP_HOST` is set.

---

## Deploy on GitHub Actions (daily, hands-off)

The workflow in [`.github/workflows/daily-newsletter.yml`](.github/workflows/daily-newsletter.yml)
runs every morning at **07:00 UTC** (editable cron) and can also be triggered
manually (with an optional dry run).

1. Push this repo to GitHub.
2. In **Settings → Secrets and variables → Actions**, add the secrets you need:
   - an analysis key — `GEMINI_API_KEY` (free) or `GROQ_API_KEY` (free) or `ANTHROPIC_API_KEY`
   - **either** `RESEND_API_KEY` **or** `SMTP_HOST` + `SMTP_PORT` + `SMTP_USER` + `SMTP_PASSWORD`
   - optionally `NEWSLETTER_TO`, `NEWSLETTER_FROM`
   - optionally, as **Variables**: `FASHION_PROVIDER`, `FASHION_MODEL`, `FASHION_EFFORT`, `FASHION_WINDOW_HOURS`, `FASHION_MAX_ARTICLES`, `FASHION_MAX_TRENDS`
3. (Optional) Trigger **Run workflow** once with *dry run* checked to preview —
   the rendered HTML is uploaded as a build artifact.

The job runs the test suite before sending, and uploads the rendered edition as
an artifact every run for easy inspection.

---

## Adding or changing sources

Edit [`config/feeds.yaml`](config/feeds.yaml) — each entry is just a `name`
and an RSS/Atom `url`. Feeds that fail on a given day are logged and skipped,
so the newsletter never breaks because one portal is down.

To change what counts as trend-signal language, edit `TREND_KEYWORDS` in
[`fashion_trends/filter.py`](fashion_trends/filter.py).

To change the verification criteria or how trends are clustered, edit the
prompt and JSON schema in
[`fashion_trends/analyze.py`](fashion_trends/analyze.py).

---

## Tests

```bash
python -m pytest -q
```

Covers the keyword/recency/dedup filtering, the analysis payload parsing +
unverified fallback, and the HTML/text rendering. No network or API key
required.

---

## Project layout

```
fashion_trends/
  config.py      env-driven settings
  sources.py     load feeds.yaml
  fetch.py       concurrent RSS fetch + normalize
  filter.py      trend-signal keyword + recency filter + dedup
  analyze.py     LLM trend-phenomenon clustering + 11-point verification dossier
  render.py      HTML + plain-text rendering
  mailer.py      Resend / SMTP delivery
  newsletter.py  pipeline orchestration
  __main__.py    CLI entry point
templates/       Jinja2 email templates
config/feeds.yaml
tests/
.github/workflows/daily-newsletter.yml
```
