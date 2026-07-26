"""Central configuration, loaded from environment variables with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = REPO_ROOT / "config" / "feeds.yaml"
DEFAULT_TEMPLATE_DIR = REPO_ROOT / "templates"

# Default model per LLM provider.
PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-opus-4-8",
}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """Runtime settings resolved from the environment."""

    # LLM analysis
    provider: str = "none"  # gemini | groq | anthropic | none
    gemini_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    model: str = ""  # empty -> provider default
    effort: str = "high"  # anthropic only

    # Delivery
    recipient: str = "nikodem.sarna@gmail.com"
    sender: str = "Fashion Trend Watch <onboarding@resend.dev>"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Behavior
    window_hours: int = 72
    max_articles: int = 60
    max_trends: int = 8
    skip_if_empty: bool = True

    # Paths
    feeds_path: Path = field(default=DEFAULT_FEEDS_PATH)
    template_dir: Path = field(default=DEFAULT_TEMPLATE_DIR)

    @classmethod
    def from_env(cls) -> "Settings":
        gemini_key = (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

        provider = os.environ.get("FASHION_PROVIDER", "").strip().lower()
        if provider not in {"gemini", "groq", "anthropic"}:
            # Auto-detect from whichever key is present (free providers first).
            if gemini_key:
                provider = "gemini"
            elif groq_key:
                provider = "groq"
            elif anthropic_key:
                provider = "anthropic"
            else:
                provider = "none"

        sender = os.environ.get("NEWSLETTER_FROM", "").strip()
        smtp_user = os.environ.get("SMTP_USER", "").strip()
        if not sender:
            sender = smtp_user or "Fashion Trend Watch <onboarding@resend.dev>"

        return cls(
            provider=provider,
            gemini_api_key=gemini_key,
            groq_api_key=groq_key,
            anthropic_api_key=anthropic_key,
            model=os.environ.get("FASHION_MODEL", "").strip(),
            effort=os.environ.get("FASHION_EFFORT", "").strip() or "high",
            recipient=os.environ.get("NEWSLETTER_TO", "").strip()
            or "nikodem.sarna@gmail.com",
            sender=sender,
            resend_api_key=os.environ.get("RESEND_API_KEY", "").strip(),
            smtp_host=os.environ.get("SMTP_HOST", "").strip(),
            smtp_port=_env_int("SMTP_PORT", 587),
            smtp_user=smtp_user,
            smtp_password=os.environ.get("SMTP_PASSWORD", "").strip(),
            window_hours=_env_int("FASHION_WINDOW_HOURS", 72),
            max_articles=_env_int("FASHION_MAX_ARTICLES", 60),
            max_trends=_env_int("FASHION_MAX_TRENDS", 8),
            skip_if_empty=_env_bool("FASHION_SKIP_IF_EMPTY", True),
        )

    @property
    def api_key(self) -> str:
        """The key for the active provider."""
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "anthropic": self.anthropic_api_key,
        }.get(self.provider, "")

    @property
    def has_analyzer(self) -> bool:
        return self.provider in PROVIDER_DEFAULT_MODELS and bool(self.api_key)

    @property
    def resolved_model(self) -> str:
        return self.model or PROVIDER_DEFAULT_MODELS.get(self.provider, "")

    @property
    def delivery_provider(self) -> str:
        if self.resend_api_key:
            return "resend"
        if self.smtp_host:
            return "smtp"
        return "none"
