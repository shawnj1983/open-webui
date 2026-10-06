"""Unit tests for the YouTube content scraper (no live network calls)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from youtube_content_scraper.scraper import (  # noqa: E402
    report_to_markdown,
    scrape_topics,
    write_report,
)
from youtube_content_scraper.topics import resolve_topics  # noqa: E402


class TopicTests(unittest.TestCase):
    def test_resolve_all_default_topics(self):
        topics = resolve_topics(None)
        self.assertEqual(
            [topic.id for topic in topics],
            ['hermes', 'crusher', 'open_source', 'make_money_ai'],
        )

    def test_resolve_subset(self):
        topics = resolve_topics(['hermes', 'make-money-ai'])
        self.assertEqual([topic.id for topic in topics], ['hermes', 'make_money_ai'])

    def test_unknown_topic_raises(self):
        with self.assertRaises(ValueError):
            resolve_topics(['not-a-topic'])


class ScraperTests(unittest.TestCase):
    def test_scrape_topics_dedupes_and_tags(self):
        fake_entries = [
            {
                'id': 'aaaaaaaaaaa',
                'title': 'Hermes Agent Demo',
                'channel': 'AI Channel',
                'description': 'Demo of Hermes',
            },
            {
                'id': 'bbbbbbbbbbb',
                'title': 'Another Hermes Video',
                'uploader': 'Dev Channel',
            },
        ]

        def fake_search(query, max_results=10, sleep_interval=0.5):
            # Return the same first video twice across queries to test dedupe.
            if 'tutorial' in query:
                return [fake_entries[0], fake_entries[1]]
            return [fake_entries[0]]

        with patch('youtube_content_scraper.scraper.search_youtube', side_effect=fake_search):
            report = scrape_topics(
                ['hermes'],
                results_per_query=5,
                include_transcripts=False,
                sleep_interval=0,
            )

        self.assertEqual(len(report.topics), 1)
        topic = report.topics[0]
        self.assertEqual(topic.topic_id, 'hermes')
        self.assertEqual(len(topic.videos), 2)
        self.assertEqual(topic.videos[0].url, 'https://www.youtube.com/watch?v=aaaaaaaaaaa')
        self.assertEqual(topic.videos[0].topic_name, 'Hermes')
        self.assertEqual(report.total_videos, 2)

        markdown = report_to_markdown(report)
        self.assertIn('# YouTube Content Scrape Report', markdown)
        self.assertIn('Hermes Agent Demo', markdown)

    def test_write_report(self):
        with patch(
            'youtube_content_scraper.scraper.search_youtube',
            return_value=[
                {
                    'id': 'ccccccccccc',
                    'title': 'Make Money with AI',
                    'channel': 'Biz',
                    'description': 'Tips',
                }
            ],
        ):
            report = scrape_topics(
                ['make_money_ai'],
                results_per_query=1,
                include_transcripts=False,
                sleep_interval=0,
            )

        out_dir = Path('/tmp/youtube_scraper_test_output')
        paths = write_report(report, out_dir, basename='unit_test_report')
        self.assertTrue(paths['json'].exists())
        self.assertTrue(paths['markdown'].exists())
        payload = json.loads(paths['json'].read_text(encoding='utf-8'))
        self.assertEqual(payload['total_videos'], 1)
        self.assertEqual(payload['topics'][0]['topic_id'], 'make_money_ai')


if __name__ == '__main__':
    unittest.main()
