from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

import anyio.to_thread
import av
import httpx
from PIL import Image

MAX_FRAMES = 6
STEP_SECONDS = 2.0
SAME_FRAME_DIFFERENCE = 6.0
MAX_VIDEO_BYTES = 60 * 1024 * 1024
THUMBNAIL = (32, 32)


class VideoFrames:
    """Text that appears later in a video is read from a few of its frames, kept as images of the post."""

    def __init__(self, folder: Path, client: httpx.AsyncClient) -> None:
        self._folder = folder
        self._client = client
        folder.mkdir(parents=True, exist_ok=True)

    async def save(self, url: str) -> list[str]:
        stem = hashlib.sha1(url.split("?")[0].encode()).hexdigest()
        known = sorted(self._folder.glob(stem + "-f*.jpg"), key=lambda path: int(path.stem.rsplit("-f", 1)[1]))
        if known:
            return [path.name for path in known]
        video = await self._download(url)
        if video is None:
            return []
        try:
            frames = await anyio.to_thread.run_sync(self._extract, video)
        except Exception:  # a broken or unsupported video leaves just the cover of its post
            return []
        names = []
        for index, jpeg in enumerate(frames):
            name = f"{stem}-f{index}.jpg"
            (self._folder / name).write_bytes(jpeg)
            names.append(name)
        return names

    async def _download(self, url: str) -> bytes | None:
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code != 200 or int(response.headers.get("content-length") or 0) > MAX_VIDEO_BYTES:
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_VIDEO_BYTES:
                        return None
        except httpx.HTTPError:
            return None
        return bytes(body)

    @classmethod
    def _extract(cls, video: bytes) -> list[bytes]:
        kept: list[tuple[Image.Image, tuple[int, ...]]] = []
        for image in cls._sampled(video):
            thumbnail = tuple(image.convert("L").resize(THUMBNAIL).tobytes())
            if not kept or cls._difference(kept[-1][1], thumbnail) >= SAME_FRAME_DIFFERENCE:
                kept.append((image, thumbnail))
        chosen = [kept[round(i * (len(kept) - 1) / (MAX_FRAMES - 1))] for i in range(MAX_FRAMES)] if len(kept) > MAX_FRAMES else kept
        return [cls._jpeg(image) for image, _ in chosen]

    @staticmethod
    def _sampled(video: bytes) -> Iterator[Image.Image]:
        """The first frame and then the first frame at or after every STEP_SECONDS."""
        with av.open(io.BytesIO(video)) as container:
            stream = container.streams.video[0]
            next_at = 0.0
            for frame in container.decode(stream):
                if frame.time is None or frame.time >= next_at:
                    yield frame.to_image()
                    next_at = (frame.time or 0.0) + STEP_SECONDS

    @staticmethod
    def _difference(first: tuple[int, ...], second: tuple[int, ...]) -> float:
        return sum(abs(a - b) for a, b in zip(first, second)) / len(first)

    @staticmethod
    def _jpeg(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=85)
        return buffer.getvalue()
