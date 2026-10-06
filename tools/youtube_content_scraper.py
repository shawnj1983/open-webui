"""
title: YouTube Content Scraper
author: Shawn Johnston
author_url: https://github.com/shawnj1983/open-webui
description: Scrape YouTube for content about Hermes, Crusher, open source apps/code, and making money with AI. Also supports custom search queries and optional transcript fetch.
version: 1.0.0
license: MIT
required_open_webui_version: 0.6.0
requirements: yt-dlp, youtube-transcript-api
"""

from __future__ import annotations

import json
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

StatusEmitter = Optional[Callable[[Any], Awaitable[None]]]

DEFAULT_TOPICS: Dict[str, Dict[str, Any]] = {
    'hermes': {
        'name': 'Hermes',
        'description': 'YouTube content about Hermes (AI agents, models, and related tools).',
        'queries': [
            'Hermes AI agent',
            'Nous Hermes LLM',
            'Hermes open source AI',
            'Hermes AI tutorial',
        ],
    },
    'crusher': {
        'name': 'Crusher',
        'description': 'YouTube content about Crusher (tools, projects, and related AI usage).',
        'queries': [
            'Crusher AI tool',
            'Crusher AI agent',
            'Crusher open source software',
            'Crusher automation app',
            'Crusher coding tool',
        ],
    },
    'open_source': {
        'name': 'Open Source Applications & Code',
        'description': 'YouTube content about open source applications and open source code of any kind.',
        'queries': [
            'open source applications',
            'open source projects 2026',
            'best open source tools',
            'open source code tutorial',
            'github open source AI apps',
        ],
    },
    'make_money_ai': {
        'name': 'Making Money with AI',
        'description': 'YouTube content about making money with AI.',
        'queries': [
            'making money with AI',
            'AI side hustle',
            'how to make money with ChatGPT',
            'AI business ideas',
            'passive income with AI',
        ],
    },
}


async def emit_status(event_emitter: StatusEmitter, description: str, done: bool = False) -> None:
    if event_emitter:
        await event_emitter({'type': 'status', 'data': {'description': description, 'done': done}})


def _search_youtube(query: str, max_results: int, sleep_interval: float) -> List[Dict[str, Any]]:
    import yt_dlp

    max_results = max(1, min(int(max_results), 50))
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'ignoreerrors': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f'ytsearch{max_results}:{query}', download=False) or {}
    if sleep_interval > 0:
        time.sleep(sleep_interval)
    return [entry for entry in (info.get('entries') or []) if entry and entry.get('id')]


def _fetch_transcript(video_id: str, languages: Sequence[str] = ('en',)) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    language_list = list(languages)
    if 'en' not in language_list:
        language_list.append('en')

    transcript_list = api.list(video_id)
    transcript = None
    for lang in language_list:
        try:
            transcript = transcript_list.find_transcript([lang])
            break
        except Exception:
            continue
    if transcript is None:
        transcript = next(iter(transcript_list), None)
    if transcript is None:
        return ''

    pieces = transcript.fetch()
    texts = []
    for piece in pieces:
        text = getattr(piece, 'text', None)
        if text is None and isinstance(piece, dict):
            text = piece.get('text', '')
        if text:
            texts.append(str(text).strip())
    return ' '.join(texts).strip()


def _format_videos(topic_name: str, videos: List[Dict[str, Any]]) -> str:
    lines = [f'## {topic_name}', f'Found **{len(videos)}** videos', '']
    for index, video in enumerate(videos, start=1):
        lines.append(f'{index}. [{video["title"]}]({video["url"]})')
        if video.get('channel'):
            lines.append(f'   - Channel: {video["channel"]}')
        lines.append(f'   - Query: `{video["query"]}`')
        if video.get('description'):
            lines.append(f'   - {video["description"][:220]}')
        if video.get('transcript'):
            preview = video['transcript'][:350].replace('\n', ' ')
            lines.append(f'   - Transcript preview: {preview}...')
        lines.append('')
    return '\n'.join(lines).rstrip()


class Tools:
    class Valves(BaseModel):
        RESULTS_PER_QUERY: int = Field(default=5, description='Videos per search query (1-20)')
        SLEEP_SECONDS: float = Field(default=0.75, description='Delay between YouTube requests')
        INCLUDE_TRANSCRIPTS: bool = Field(
            default=False,
            description='Fetch transcripts for top videos (slower)',
        )
        MAX_TRANSCRIPTS_PER_TOPIC: int = Field(
            default=3,
            description='Max transcripts to fetch per topic when enabled',
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def list_scrape_topics(
        self,
        __event_emitter__: StatusEmitter = None,
    ) -> str:
        """
        List the built-in YouTube scrape topics (Hermes, Crusher, open source, making money with AI).
        """
        await emit_status(__event_emitter__, 'Listing scrape topics', done=True)
        payload = {
            topic_id: {
                'name': meta['name'],
                'description': meta['description'],
                'queries': meta['queries'],
            }
            for topic_id, meta in DEFAULT_TOPICS.items()
        }
        return json.dumps(payload, indent=2)

    async def scrape_youtube_topics(
        self,
        topics: str = 'all',
        results_per_query: Optional[int] = None,
        include_transcripts: Optional[bool] = None,
        __event_emitter__: StatusEmitter = None,
    ) -> str:
        """
        Scrape YouTube for configured content topics.

        Args:
            topics: Comma-separated topic ids, or "all".
                    Options: hermes, crusher, open_source, make_money_ai
            results_per_query: Override valves max results per query.
            include_transcripts: Override whether to fetch transcripts.
        """
        try:
            selected_ids = self._parse_topic_ids(topics)
        except ValueError as exc:
            return f'Error: {exc}'

        per_query = results_per_query or self.valves.RESULTS_PER_QUERY
        per_query = max(1, min(int(per_query), 20))
        with_transcripts = (
            self.valves.INCLUDE_TRANSCRIPTS if include_transcripts is None else include_transcripts
        )

        sections: List[str] = ['# YouTube Content Scrape', '']
        total = 0

        try:
            for topic_id in selected_ids:
                meta = DEFAULT_TOPICS[topic_id]
                await emit_status(__event_emitter__, f'Scraping topic: {meta["name"]}')
                videos, errors = self._scrape_queries(
                    queries=meta['queries'],
                    topic_id=topic_id,
                    results_per_query=per_query,
                    include_transcripts=with_transcripts,
                )
                total += len(videos)
                sections.append(_format_videos(meta['name'], videos))
                if errors:
                    sections.append('Errors:')
                    sections.extend([f'- {error}' for error in errors])
                    sections.append('')
        except ImportError as exc:
            return f'Error: {exc}'

        await emit_status(
            __event_emitter__,
            f'Scrape complete: {total} videos across {len(selected_ids)} topics',
            done=True,
        )
        sections.insert(2, f'Total videos: **{total}**')
        sections.insert(3, '')
        return '\n'.join(sections).rstrip()

    async def search_youtube_content(
        self,
        query: str,
        max_results: Optional[int] = None,
        include_transcript: bool = False,
        __event_emitter__: StatusEmitter = None,
    ) -> str:
        """
        Search YouTube for a custom content query and return matching videos.

        Args:
            query: Free-form YouTube search query.
            max_results: Number of videos to return.
            include_transcript: Fetch transcript for the first result.
        """
        if not query or not query.strip():
            return 'Error: query is required.'

        limit = max_results or self.valves.RESULTS_PER_QUERY
        limit = max(1, min(int(limit), 20))
        await emit_status(__event_emitter__, f'Searching YouTube for: {query}')

        try:
            entries = _search_youtube(query.strip(), limit, self.valves.SLEEP_SECONDS)
        except Exception as exc:
            return f'Error searching YouTube: {exc}'

        videos = [self._entry_to_dict(entry, query=query.strip(), topic_id='custom') for entry in entries]
        if include_transcript and videos:
            try:
                videos[0]['transcript'] = _fetch_transcript(videos[0]['video_id'])
            except Exception as exc:
                videos[0]['transcript_error'] = str(exc)

        await emit_status(__event_emitter__, f'Found {len(videos)} videos', done=True)
        return _format_videos(f'Search: {query.strip()}', videos)

    async def get_youtube_transcript(
        self,
        video_id_or_url: str,
        __event_emitter__: StatusEmitter = None,
    ) -> str:
        """
        Fetch the transcript text for a YouTube video id or URL.

        Args:
            video_id_or_url: A YouTube video id (11 chars) or full watch URL.
        """
        video_id = self._parse_video_id(video_id_or_url)
        if not video_id:
            return 'Error: could not parse a valid YouTube video id.'

        await emit_status(__event_emitter__, f'Fetching transcript for {video_id}')
        try:
            transcript = _fetch_transcript(video_id)
        except Exception as exc:
            return f'Error fetching transcript: {exc}'

        await emit_status(__event_emitter__, 'Transcript fetched', done=True)
        if not transcript:
            return f'No transcript available for `{video_id}`.'
        return f'Transcript for https://www.youtube.com/watch?v={video_id}\n\n{transcript}'

    def _parse_topic_ids(self, topics: str) -> List[str]:
        raw = (topics or 'all').strip().lower()
        if raw in {'all', '*', ''}:
            return list(DEFAULT_TOPICS.keys())

        selected: List[str] = []
        for part in raw.replace(' ', '').split(','):
            key = part.replace('-', '_')
            if key not in DEFAULT_TOPICS:
                known = ', '.join(DEFAULT_TOPICS.keys())
                raise ValueError(f'Unknown topic "{part}". Known topics: {known}')
            selected.append(key)
        return selected

    def _scrape_queries(
        self,
        *,
        queries: List[str],
        topic_id: str,
        results_per_query: int,
        include_transcripts: bool,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        videos: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen: set[str] = set()

        for query in queries:
            try:
                entries = _search_youtube(query, results_per_query, self.valves.SLEEP_SECONDS)
            except Exception as exc:
                errors.append(f'Search failed for "{query}": {exc}')
                continue
            for entry in entries:
                video = self._entry_to_dict(entry, query=query, topic_id=topic_id)
                if not video['video_id'] or video['video_id'] in seen:
                    continue
                seen.add(video['video_id'])
                videos.append(video)

        if include_transcripts:
            for video in videos[: self.valves.MAX_TRANSCRIPTS_PER_TOPIC]:
                try:
                    video['transcript'] = _fetch_transcript(video['video_id'])
                    if self.valves.SLEEP_SECONDS > 0:
                        time.sleep(self.valves.SLEEP_SECONDS)
                except Exception as exc:
                    video['transcript_error'] = str(exc)
                    errors.append(f'Transcript failed for {video["video_id"]}: {exc}')

        return videos, errors

    def _entry_to_dict(self, entry: Dict[str, Any], *, query: str, topic_id: str) -> Dict[str, Any]:
        video_id = str(entry.get('id') or '')
        url = entry.get('webpage_url') or entry.get('url') or f'https://www.youtube.com/watch?v={video_id}'
        if video_id and 'youtube.com' not in str(url) and 'youtu.be' not in str(url):
            url = f'https://www.youtube.com/watch?v={video_id}'
        description = str(entry.get('description') or '')
        if len(description) > 500:
            description = description[:497] + '...'
        return {
            'video_id': video_id,
            'title': str(entry.get('title') or 'Untitled'),
            'url': str(url),
            'channel': str(entry.get('channel') or entry.get('uploader') or ''),
            'description': description,
            'query': query,
            'topic_id': topic_id,
            'transcript': '',
        }

    def _parse_video_id(self, value: str) -> str:
        text = (value or '').strip()
        if not text:
            return ''
        if 'youtube.com' in text or 'youtu.be' in text:
            if 'v=' in text:
                return text.split('v=')[1].split('&')[0][:11]
            return text.rstrip('/').split('/')[-1][:11]
        return text[:11] if len(text) >= 11 else text
