from __future__ import annotations

import hashlib
import io
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

    async def save(self, url: str, cover: Path | None = None) -> list[str]:
        """Never raises: a video that cannot be read leaves just the cover of its post. The opening frames that repeat
        the cover, already an image of the post, are left out."""
        stem = hashlib.sha1(url.split("?")[0].encode()).hexdigest()
        known = sorted(self._folder.glob(stem + "-f*.jpg"), key=lambda path: int(path.stem.rsplit("-f", 1)[1]))
        if known:
            return [path.name for path in known]
        try:
            video = await self._download(url)
            frames = await anyio.to_thread.run_sync(self._extract, video, cover) if video else []
            return self._write(stem, frames)
        except Exception:
            return []

    def _write(self, stem: str, frames: list[bytes]) -> list[str]:
        """Written under temporary names first, so a crash never leaves a part of the set that looks complete."""
        names = [f"{stem}-f{index}.jpg" for index in range(len(frames))]
        temporary = [self._folder / (name + ".tmp") for name in names]
        try:
            for path, jpeg in zip(temporary, frames):
                path.write_bytes(jpeg)
            for path, name in zip(temporary, names):
                path.replace(self._folder / name)
        finally:
            for path in temporary:
                path.unlink(missing_ok=True)
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
    def _extract(cls, video: bytes, cover: Path | None) -> list[bytes]:
        kept = cls._after_cover(cls._scan(video), cls._cover_thumbnail(cover))
        chosen = [kept[round(i * (len(kept) - 1) / (MAX_FRAMES - 1))] for i in range(MAX_FRAMES)] if len(kept) > MAX_FRAMES else kept
        return [jpeg for jpeg, _ in chosen]

    @classmethod
    def _scan(cls, video: bytes) -> list[tuple[bytes, bytes]]:
        """JPEG and thumbnail of every sampled frame that differs from the one before it; no full-size image outlives its turn."""
        kept: list[tuple[bytes, bytes]] = []
        with av.open(io.BytesIO(video)) as container:
            stream = container.streams.video[0]
            next_at = 0.0
            for frame in container.decode(stream):
                if frame.time is not None and frame.time < next_at:
                    continue
                next_at = (frame.time or 0.0) + STEP_SECONDS
                image = frame.to_image()
                thumbnail = cls._thumbnail(image)
                if not kept or cls._difference(kept[-1][1], thumbnail) >= SAME_FRAME_DIFFERENCE:
                    kept.append((cls._jpeg(image), thumbnail))
        return kept

    @classmethod
    def _after_cover(cls, kept: list[tuple[bytes, bytes]], cover: bytes | None) -> list[tuple[bytes, bytes]]:
        if cover is None:
            return kept
        repeating = 0
        while repeating < len(kept) and cls._difference(cover, kept[repeating][1]) < SAME_FRAME_DIFFERENCE:
            repeating += 1
        return kept[repeating:]

    @classmethod
    def _cover_thumbnail(cls, cover: Path | None) -> bytes | None:
        """None when there is no cover or it cannot be read."""
        if cover is None:
            return None
        try:
            with Image.open(cover) as image:
                return cls._thumbnail(image)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _thumbnail(image: Image.Image) -> bytes:
        return image.convert("L").resize(THUMBNAIL).tobytes()

    @staticmethod
    def _difference(first: bytes, second: bytes) -> float:
        return sum(abs(a - b) for a, b in zip(first, second)) / len(first)

    @staticmethod
    def _jpeg(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=85)
        return buffer.getvalue()
