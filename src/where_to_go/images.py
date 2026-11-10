from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_MEDIA_TYPES = {extension: media_type for media_type, extension in _EXTENSIONS.items()}


class ImageStore:
    """Telegram CDN links expire, so post images are kept locally."""

    def __init__(self, folder: Path, client: httpx.AsyncClient) -> None:
        self._folder = folder
        self._client = client
        folder.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path | None:
        candidate = (self._folder / name).resolve()
        if candidate.parent != self._folder.resolve() or not candidate.is_file():
            return None
        return candidate

    def load(self, name: str) -> tuple[str, bytes] | None:
        """The media type and bytes of a stored image."""
        path = self.path(name)
        media_type = _MEDIA_TYPES.get(path.suffix) if path else None
        return (media_type, path.read_bytes()) if path and media_type else None

    async def save(self, url: str) -> str | None:
        stem = hashlib.sha1(url.split("?")[0].encode()).hexdigest()
        existing = next(self._folder.glob(stem + ".*"), None)
        if existing:
            return existing.name
        try:
            response = await self._client.get(url)
        except httpx.HTTPError:
            return None
        extension = _EXTENSIONS.get(response.headers.get("content-type", "").split(";")[0])
        if response.status_code != 200 or extension is None:
            return None
        name = stem + extension
        (self._folder / name).write_bytes(response.content)
        return name
