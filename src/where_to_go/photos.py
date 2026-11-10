from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import ValidationError

from where_to_go.images import ImageStore
from where_to_go.llm import JsonLlm, LlmImage
from where_to_go.models import PhotoReading, PhotoReadings, PhotoText, Post
from where_to_go.reading_rules import ReadingRules
from where_to_go.repositories import PhotoTextRepository


class PhotoTranscriber:
    """Turns post photos into text once, so posts are read as text and every photo goes to Claude only once."""

    BATCH_SIZE = 7
    PER_POST = 10
    """A Telegram album holds at most ten."""

    def __init__(self, llm: JsonLlm, images: ImageStore, texts: PhotoTextRepository, prompt: Callable[[], str]) -> None:
        self._llm = llm
        self._images = images
        self._texts = texts
        self._prompt = prompt

    @classmethod
    def shown(cls, post: Post) -> list[str]:
        return post.image_paths[: cls.PER_POST]

    @staticmethod
    def rules() -> str:
        return ReadingRules.PHOTOS

    def untranscribed(self, posts: Iterable[Post]) -> list[str]:
        """Stored photos of these posts that have no text under the current rules; a lost file has nothing to read."""
        names = list(dict.fromkeys(name for post in posts for name in self.shown(post) if self._images.path(name)))
        rules = self.rules()
        done = self._texts.of(names)
        return [name for name in names if name not in done or done[name].read_with != rules]

    def batches(self, names: list[str]) -> list[list[str]]:
        return [names[i : i + self.BATCH_SIZE] for i in range(0, len(names), self.BATCH_SIZE)]

    async def transcribe(self, names: list[str]) -> None:
        """Saves the text of every photo Claude answered for; the rest stay untranscribed and are retried next time."""
        loaded = [(name, self._images.load(name)) for name in names]
        pictures = [(name, picture) for name, picture in loaded if picture]
        if not pictures:
            return
        rules = self.rules()
        answer = await self._llm.complete_json(
            self._prompt(),
            f"Transcribe these {len(pictures)} photos.",
            PhotoReadings.model_json_schema(),
            [LlmImage(f"Photo {number}:", *picture) for number, (_, picture) in enumerate(pictures)],
        )
        texts = []
        for reading in self._readings(answer):
            if 0 <= reading.photo < len(pictures):
                texts.append(PhotoText(image=pictures[reading.photo][0], text=reading.text, shows=reading.shows, read_with=rules))
        self._texts.save(texts)

    @staticmethod
    def _readings(answer: dict[str, Any]) -> list[PhotoReading]:
        readings = []
        for raw in answer.get("photos", []):
            try:
                readings.append(PhotoReading.model_validate(raw))
            except ValidationError:
                continue
        return readings
