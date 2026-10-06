"""YouTube content scraper powered by yt-dlp (optional transcript fetch)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .topics import Topic, resolve_topics

log = logging.getLogger(__name__)


@dataclass
class VideoResult:
    video_id: str
    title: str
    url: str
    channel: str = ''
    description: str = ''
    duration: Optional[int] = None
    view_count: Optional[int] = None
    upload_date: str = ''
    thumbnail: str = ''
    query: str = ''
    topic_id: str = ''
    topic_name: str = ''
    transcript: str = ''
    transcript_error: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopicScrapeResult:
    topic_id: str
    topic_name: str
    description: str
    queries: List[str]
    videos: List[VideoResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'topic_id': self.topic_id,
            'topic_name': self.topic_name,
            'description': self.description,
            'queries': self.queries,
            'video_count': len(self.videos),
            'videos': [video.to_dict() for video in self.videos],
            'errors': self.errors,
        }


@dataclass
class ScrapeReport:
    scraped_at: str
    results_per_query: int
    include_transcripts: bool
    topics: List[TopicScrapeResult] = field(default_factory=list)

    @property
    def total_videos(self) -> int:
        return sum(len(topic.videos) for topic in self.topics)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'scraped_at': self.scraped_at,
            'results_per_query': self.results_per_query,
            'include_transcripts': self.include_transcripts,
            'topic_count': len(self.topics),
            'total_videos': self.total_videos,
            'topics': [topic.to_dict() for topic in self.topics],
        }


ProgressCallback = Callable[[str], None]


def _noop_progress(_: str) -> None:
    return None


def search_youtube(
    query: str,
    max_results: int = 10,
    *,
    sleep_interval: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Search YouTube via yt-dlp flat extraction.

    Returns a list of raw entry dicts from yt-dlp.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise ImportError(
            'yt-dlp is required. Install with: pip install yt-dlp'
        ) from exc

    max_results = max(1, min(int(max_results), 50))
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'ignoreerrors': True,
    }

    search_term = f'ytsearch{max_results}:{query}'
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search_term, download=False) or {}

    if sleep_interval > 0:
        time.sleep(sleep_interval)

    entries = info.get('entries') or []
    return [entry for entry in entries if entry and entry.get('id')]


def fetch_transcript(video_id: str, languages: Sequence[str] = ('en',)) -> str:
    """Fetch a YouTube transcript for a video id. Returns empty string on failure."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise ImportError(
            'youtube-transcript-api is required for transcripts. '
            'Install with: pip install youtube-transcript-api'
        ) from exc

    api = YouTubeTranscriptApi()
    language_list = list(languages)
    if 'en' not in language_list:
        language_list.append('en')

    try:
        transcript_list = api.list(video_id)
        transcript = None
        for lang in language_list:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue
        if transcript is None:
            # Fall back to any generated/manual transcript available.
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
    except Exception as exc:
        log.debug('Transcript fetch failed for %s: %s', video_id, exc)
        raise


def _entry_to_video(
    entry: Dict[str, Any],
    *,
    query: str,
    topic: Topic,
) -> VideoResult:
    video_id = str(entry.get('id') or '')
    url = entry.get('url') or entry.get('webpage_url') or f'https://www.youtube.com/watch?v={video_id}'
    if video_id and 'youtube.com' not in url and 'youtu.be' not in url:
        url = f'https://www.youtube.com/watch?v={video_id}'

    description = entry.get('description') or entry.get('title') or ''
    if isinstance(description, str) and len(description) > 500:
        description = description[:497] + '...'

    duration = entry.get('duration')
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = None

    view_count = entry.get('view_count')
    if view_count is not None:
        try:
            view_count = int(view_count)
        except (TypeError, ValueError):
            view_count = None

    thumbnail = entry.get('thumbnail') or ''
    if not thumbnail:
        thumbnails = entry.get('thumbnails') or []
        if thumbnails and isinstance(thumbnails[-1], dict):
            thumbnail = thumbnails[-1].get('url') or ''

    return VideoResult(
        video_id=video_id,
        title=str(entry.get('title') or 'Untitled'),
        url=url,
        channel=str(entry.get('channel') or entry.get('uploader') or ''),
        description=str(description),
        duration=duration,
        view_count=view_count,
        upload_date=str(entry.get('upload_date') or ''),
        thumbnail=str(thumbnail),
        query=query,
        topic_id=topic.id,
        topic_name=topic.name,
    )


def scrape_topic(
    topic: Topic,
    *,
    results_per_query: int = 8,
    include_transcripts: bool = False,
    transcript_languages: Sequence[str] = ('en',),
    sleep_interval: float = 0.75,
    max_transcripts_per_topic: int = 5,
    progress: ProgressCallback = _noop_progress,
) -> TopicScrapeResult:
    """Scrape all queries for one topic and de-duplicate videos by id."""
    result = TopicScrapeResult(
        topic_id=topic.id,
        topic_name=topic.name,
        description=topic.description,
        queries=list(topic.queries),
    )
    seen: set[str] = set()

    for query in topic.queries:
        progress(f'[{topic.name}] Searching: {query}')
        try:
            entries = search_youtube(query, max_results=results_per_query, sleep_interval=sleep_interval)
        except Exception as exc:
            message = f'Search failed for "{query}": {exc}'
            log.warning(message)
            result.errors.append(message)
            continue

        for entry in entries:
            video = _entry_to_video(entry, query=query, topic=topic)
            if not video.video_id or video.video_id in seen:
                continue
            seen.add(video.video_id)
            result.videos.append(video)

    if include_transcripts and result.videos:
        progress(f'[{topic.name}] Fetching transcripts (up to {max_transcripts_per_topic})...')
        for video in result.videos[:max_transcripts_per_topic]:
            try:
                video.transcript = fetch_transcript(video.video_id, languages=transcript_languages)
                if sleep_interval > 0:
                    time.sleep(sleep_interval)
            except Exception as exc:
                video.transcript_error = str(exc)
                result.errors.append(f'Transcript failed for {video.video_id}: {exc}')

    progress(f'[{topic.name}] Found {len(result.videos)} unique videos')
    return result


def scrape_topics(
    topic_ids: Optional[Sequence[str]] = None,
    *,
    results_per_query: int = 8,
    include_transcripts: bool = False,
    transcript_languages: Sequence[str] = ('en',),
    sleep_interval: float = 0.75,
    max_transcripts_per_topic: int = 5,
    progress: ProgressCallback = _noop_progress,
) -> ScrapeReport:
    """Scrape one or more preset topics (defaults to all)."""
    topics = resolve_topics(list(topic_ids) if topic_ids else None)
    report = ScrapeReport(
        scraped_at=datetime.now(timezone.utc).isoformat(),
        results_per_query=results_per_query,
        include_transcripts=include_transcripts,
    )

    for topic in topics:
        report.topics.append(
            scrape_topic(
                topic,
                results_per_query=results_per_query,
                include_transcripts=include_transcripts,
                transcript_languages=transcript_languages,
                sleep_interval=sleep_interval,
                max_transcripts_per_topic=max_transcripts_per_topic,
                progress=progress,
            )
        )

    return report


def scrape_custom_queries(
    queries: Iterable[str],
    *,
    topic_id: str = 'custom',
    topic_name: str = 'Custom',
    results_per_query: int = 8,
    include_transcripts: bool = False,
    sleep_interval: float = 0.75,
    progress: ProgressCallback = _noop_progress,
) -> TopicScrapeResult:
    """Scrape arbitrary search queries under a synthetic topic."""
    query_list = [q.strip() for q in queries if q and q.strip()]
    topic = Topic(
        id=topic_id,
        name=topic_name,
        description='Custom query scrape',
        queries=query_list,
    )
    return scrape_topic(
        topic,
        results_per_query=results_per_query,
        include_transcripts=include_transcripts,
        sleep_interval=sleep_interval,
        progress=progress,
    )


def report_to_markdown(report: ScrapeReport) -> str:
    """Render a scrape report as readable Markdown."""
    lines: List[str] = [
        '# YouTube Content Scrape Report',
        '',
        f'- Scraped at: `{report.scraped_at}`',
        f'- Topics: **{len(report.topics)}**',
        f'- Total unique videos: **{report.total_videos}**',
        f'- Results per query: **{report.results_per_query}**',
        f'- Transcripts included: **{report.include_transcripts}**',
        '',
    ]

    for topic in report.topics:
        lines.extend(
            [
                f'## {topic.topic_name}',
                '',
                topic.description,
                '',
                f'Queries: {", ".join(f"`{q}`" for q in topic.queries)}',
                '',
                f'Videos found: **{len(topic.videos)}**',
                '',
            ]
        )
        if topic.errors:
            lines.append('Errors:')
            for err in topic.errors:
                lines.append(f'- {err}')
            lines.append('')

        if not topic.videos:
            lines.extend(['_No videos found._', ''])
            continue

        for index, video in enumerate(topic.videos, start=1):
            meta_bits = []
            if video.channel:
                meta_bits.append(video.channel)
            if video.view_count is not None:
                meta_bits.append(f'{video.view_count:,} views')
            if video.duration is not None:
                minutes, seconds = divmod(int(video.duration), 60)
                meta_bits.append(f'{minutes}:{seconds:02d}')
            meta = ' · '.join(meta_bits)
            lines.append(f'{index}. [{video.title}]({video.url})')
            if meta:
                lines.append(f'   - {meta}')
            lines.append(f'   - Query: `{video.query}`')
            if video.description:
                lines.append(f'   - {video.description}')
            if video.transcript:
                preview = video.transcript[:400].replace('\n', ' ')
                lines.append(f'   - Transcript preview: {preview}...')
            lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def write_report(
    report: ScrapeReport,
    output_dir: str | Path,
    *,
    basename: str = 'youtube_scrape',
) -> Dict[str, Path]:
    """Write JSON and Markdown report files. Returns written paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f'{basename}.json'
    md_path = out / f'{basename}.md'

    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    md_path.write_text(report_to_markdown(report), encoding='utf-8')
    return {'json': json_path, 'markdown': md_path}
