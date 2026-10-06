"""Preset YouTube scrape topics for the content scraper agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Topic:
    """A named content topic with one or more YouTube search queries."""

    id: str
    name: str
    description: str
    queries: List[str]


# Default topics requested for this scraper agent.
DEFAULT_TOPICS: List[Topic] = [
    Topic(
        id='hermes',
        name='Hermes',
        description='YouTube content about Hermes (AI agents, models, and related tools).',
        queries=[
            'Hermes AI agent',
            'Nous Hermes LLM',
            'Hermes open source AI',
            'Hermes AI tutorial',
        ],
    ),
    Topic(
        id='crusher',
        name='Crusher',
        description='YouTube content about Crusher (tools, projects, and related AI usage).',
        queries=[
            'Crusher AI tool',
            'Crusher AI agent',
            'Crusher open source software',
            'Crusher automation app',
            'Crusher coding tool',
        ],
    ),
    Topic(
        id='open_source',
        name='Open Source Applications & Code',
        description='YouTube content about open source applications and open source code of any kind.',
        queries=[
            'open source applications',
            'open source projects 2026',
            'best open source tools',
            'open source code tutorial',
            'github open source AI apps',
        ],
    ),
    Topic(
        id='make_money_ai',
        name='Making Money with AI',
        description='YouTube content about making money with AI.',
        queries=[
            'making money with AI',
            'AI side hustle',
            'how to make money with ChatGPT',
            'AI business ideas',
            'passive income with AI',
        ],
    ),
]


TOPIC_BY_ID: Dict[str, Topic] = {topic.id: topic for topic in DEFAULT_TOPICS}


def list_topic_ids() -> List[str]:
    return [topic.id for topic in DEFAULT_TOPICS]


def resolve_topics(topic_ids: List[str] | None = None) -> List[Topic]:
    """Resolve topic ids to Topic objects. None/empty means all default topics."""
    if not topic_ids:
        return list(DEFAULT_TOPICS)

    resolved: List[Topic] = []
    unknown: List[str] = []
    for topic_id in topic_ids:
        key = topic_id.strip().lower().replace('-', '_').replace(' ', '_')
        topic = TOPIC_BY_ID.get(key)
        if topic is None:
            unknown.append(topic_id)
        else:
            resolved.append(topic)

    if unknown:
        known = ', '.join(list_topic_ids())
        raise ValueError(f'Unknown topic id(s): {", ".join(unknown)}. Known topics: {known}')

    return resolved
