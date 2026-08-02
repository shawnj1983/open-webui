#!/usr/bin/env python3
"""CLI for scraping YouTube content across configured topics."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/youtube_content_scraper/cli.py`
if __name__ == '__main__' and (__package__ is None or __package__ == ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from youtube_content_scraper.scraper import report_to_markdown, scrape_topics, write_report
    from youtube_content_scraper.topics import list_topic_ids
else:
    from .scraper import report_to_markdown, scrape_topics, write_report
    from .topics import list_topic_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Scrape YouTube for content about Hermes, Crusher, open source apps/code, '
            'and making money with AI.'
        )
    )
    parser.add_argument(
        '--topics',
        nargs='*',
        default=None,
        help=f'Topic ids to scrape (default: all). Options: {", ".join(list_topic_ids())}',
    )
    parser.add_argument(
        '--results-per-query',
        type=int,
        default=8,
        help='Max videos to pull per search query (1-50, default: 8)',
    )
    parser.add_argument(
        '--transcripts',
        action='store_true',
        help='Also fetch transcripts for the first few videos per topic',
    )
    parser.add_argument(
        '--max-transcripts-per-topic',
        type=int,
        default=5,
        help='Max transcripts to fetch per topic when --transcripts is set (default: 5)',
    )
    parser.add_argument(
        '--sleep',
        type=float,
        default=0.75,
        help='Seconds to sleep between YouTube requests (default: 0.75)',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('scripts/youtube_content_scraper/output'),
        help='Directory for JSON/Markdown reports',
    )
    parser.add_argument(
        '--basename',
        default='youtube_scrape',
        help='Base filename for report outputs (default: youtube_scrape)',
    )
    parser.add_argument(
        '--print-markdown',
        action='store_true',
        help='Print the Markdown report to stdout',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(levelname)s %(message)s',
    )

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    try:
        report = scrape_topics(
            args.topics,
            results_per_query=args.results_per_query,
            include_transcripts=args.transcripts,
            sleep_interval=args.sleep,
            max_transcripts_per_topic=args.max_transcripts_per_topic,
            progress=progress,
        )
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    paths = write_report(report, args.output_dir, basename=args.basename)
    print(f'Wrote {paths["json"]}', file=sys.stderr)
    print(f'Wrote {paths["markdown"]}', file=sys.stderr)
    print(
        f'Scrape complete: {report.total_videos} videos across {len(report.topics)} topics',
        file=sys.stderr,
    )

    if args.print_markdown:
        print(report_to_markdown(report), end='')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
