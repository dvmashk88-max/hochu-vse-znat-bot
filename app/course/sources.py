from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from html.parser import HTMLParser

import requests

from app.course.models import CourseDay, RetrievedSource, Source

logger = logging.getLogger(__name__)


class SourceRetrievalError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class SourceRetriever:
    def __init__(self, timeout: int = 20, max_chars: int = 12_000):
        self.timeout = timeout
        self.max_chars = max_chars

    def _fetch(self, source: Source) -> RetrievedSource:
        response = requests.get(
            source.url,
            headers={"User-Agent": "HochuVseZnatCourseBot/1.0"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" in content_type:
            parser = _TextExtractor()
            parser.feed(response.text)
            text = " ".join(parser.parts)
        elif "text" in content_type or "json" in content_type:
            text = response.text
        else:
            raise SourceRetrievalError(f"Unsupported source content type: {content_type}")
        text = re.sub(r"\s+", " ", text).strip()[: self.max_chars]
        if len(text) < 200:
            raise SourceRetrievalError("Source returned too little readable text")
        return RetrievedSource(source, text, hashlib.sha256(text.encode()).hexdigest())

    async def retrieve(self, lesson: CourseDay) -> tuple[RetrievedSource, ...]:
        results = await asyncio.gather(
            *(asyncio.to_thread(self._fetch, source) for source in lesson.sources),
            return_exceptions=True,
        )
        retrieved = []
        retrieved_required = []
        for source, result in zip(lesson.sources, results):
            if isinstance(result, Exception):
                logger.warning("Course source failed: %s (%s)", source.url, result)
            else:
                retrieved.append(result)
                if source.required:
                    retrieved_required.append(result)
        required_exist = any(source.required for source in lesson.sources)
        if not retrieved or (required_exist and not retrieved_required):
            raise SourceRetrievalError(
                "No required course source could be retrieved"
            )
        return tuple(retrieved)
