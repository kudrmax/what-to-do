"""Releases published on GitHub, for the app installed from a disk image: it has no git to ask.

A release counts once its disk image for this kind of Mac is attached: the release workflow builds the
images a few minutes after the release is published, and an update must not start before.

Imports only the standard library: the updater relies on it while it replaces the bundle under itself."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from where_to_go.launcher.bundle import GITHUB_REPO, DiskImageName

API_ENV = "WHERE_TO_GO_GITHUB_API"
RAW_ENV = "WHERE_TO_GO_GITHUB_RAW"
DEFAULT_API = "https://api.github.com"
DEFAULT_RAW = "https://raw.githubusercontent.com"
TIMEOUT_S = 20
RELEASES_PER_PAGE = 20
TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


class ReleaseFeedError(RuntimeError):
    """GitHub could not be reached or answered something else than releases."""


@dataclass(frozen=True)
class PublishedImage:
    version: tuple[int, int, int]
    url: str
    size: int
    sha256: str | None

    @property
    def tag(self) -> str:
        return "v" + self.version_text

    @property
    def version_text(self) -> str:
        return ".".join(map(str, self.version))


Fetch = Callable[[str], bytes]


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "what-to-do-app", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 — fixed https addresses
            return bytes(response.read())
    except (OSError, urllib.error.URLError) as error:
        raise ReleaseFeedError(f"{url}: {error}") from error


class GitHubReleaseFeed:
    def __init__(self, image: DiskImageName, environ: Mapping[str, str] = os.environ, get: Fetch = fetch, repo: str = GITHUB_REPO) -> None:
        self._image = image
        self._get = get
        self._repo = repo
        self._api = (environ.get(API_ENV) or DEFAULT_API).rstrip("/")
        self._raw = (environ.get(RAW_ENV) or DEFAULT_RAW).rstrip("/")

    def latest(self) -> PublishedImage | None:
        """The newest release with a disk image for this Mac; None when there is none yet."""
        try:
            releases = json.loads(self._get(f"{self._api}/repos/{self._repo}/releases?per_page={RELEASES_PER_PAGE}"))
        except ValueError as error:
            raise ReleaseFeedError(f"GitHub answered something else than releases: {error}") from error
        if not isinstance(releases, list):
            raise ReleaseFeedError("GitHub answered something else than releases")
        images = [image for release in releases if (image := self._image_of(release)) is not None]
        return max(images, key=lambda image: image.version, default=None)

    def file(self, version: str, path: str) -> bytes:
        """A file of the repository as it was at the release."""
        return self._get(f"{self._raw}/{self._repo}/v{version}/{path}")

    def _image_of(self, release: object) -> PublishedImage | None:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            return None
        match = TAG.fullmatch(str(release.get("tag_name", "")))
        if match is None:
            return None
        version = (int(match[1]), int(match[2]), int(match[3]))
        name = self._image.of(".".join(map(str, version)))
        for asset in release.get("assets") or []:
            if isinstance(asset, dict) and asset.get("name") == name and asset.get("browser_download_url"):
                digest = str(asset.get("digest") or "")
                return PublishedImage(
                    version=version,
                    url=str(asset["browser_download_url"]),
                    size=int(asset.get("size") or 0),
                    sha256=digest.removeprefix("sha256:") if digest.startswith("sha256:") else None,
                )
        return None
