"""Command-line entry point: `python -m fashion_trends`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Settings
from .newsletter import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fashion_trends",
        description="Build and email the daily fashion-trend-verification newsletter.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the edition but do not send it.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test edition now, even if there are no live trends "
        "(uses sample content as a fallback). Subject is prefixed [TEST].",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the rendered HTML to this path (useful with --dry-run).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ...). Default: INFO.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()

    if not args.dry_run and settings.delivery_provider == "none":
        logging.error(
            "No delivery provider configured. Set RESEND_API_KEY or SMTP_* "
            "variables, or use --dry-run."
        )
        return 2

    from .mailer import DeliveryError

    try:
        result = run(
            settings,
            dry_run=args.dry_run,
            test_mode=args.test,
            output_path=args.output,
        )
    except DeliveryError as exc:
        logging.error("Delivery failed: %s", exc)
        print(
            "Could not send the email. Check your delivery credentials "
            "(SMTP_* / RESEND_API_KEY). Details above."
        )
        return 1

    if result.skipped_reason == "no_trends":
        print("No trend-signal stories today — nothing sent.")
        return 0
    if result.sent:
        print(
            f"Sent edition with {result.trend_count} trend dossiers "
            f"(from {result.article_count} articles) to {settings.recipient}."
        )
    else:
        print(
            f"Built edition with {result.trend_count} trend dossiers "
            f"(from {result.article_count} articles) (not sent)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
