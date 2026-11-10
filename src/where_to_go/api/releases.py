from __future__ import annotations

import mimetypes
import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from markdown_it import MarkdownIt
from pydantic import BaseModel

from where_to_go.container import Container
from where_to_go.releases import AppVersion, ChangelogEntry, Releases
from where_to_go.updating import UpdateAlreadyRunningError, UpdateProgress

TAG = "releases"
TAG_HELP = "The installed version, its changelog and updating to a newer release"

ASSETS_PATH = "/changelog/assets"
# A changelog image as the markdown names it, by its repository path.
IMAGE_SRC = re.compile(r'src="(docs/images/changelog/(\d+\.\d+\.\d+)/[^"]*)"')
_markdown = MarkdownIt("commonmark", {"html": False})


class VersionView(BaseModel):
    version: str


class ChangelogSectionView(BaseModel):
    title: str
    html: str


class ChangelogEntryView(BaseModel):
    version: str
    released_on: date
    summary: str
    sections: list[ChangelogSectionView]


class UpdateStatusView(BaseModel):
    current: str
    latest: str | None
    available: bool
    entries: list[ChangelogEntryView]
    check_failed: bool
    restart_command: str
    update_command: str


class ChangelogPages:
    """Changelog entries as the page shows them: sections rendered to HTML, images served by the API."""

    def __init__(self, request: Request) -> None:
        # Under the interface the API lives at /api; images must point there too.
        self._assets = request.scope.get("root_path", "") + ASSETS_PATH

    def entries(self, entries: list[ChangelogEntry]) -> list[ChangelogEntryView]:
        return [self._entry(entry) for entry in entries]

    def _entry(self, entry: ChangelogEntry) -> ChangelogEntryView:
        return ChangelogEntryView(
            version=entry.version,
            released_on=entry.released_on,
            summary=entry.summary,
            sections=[ChangelogSectionView(title=section.title, html=self._html(section.body_markdown)) for section in entry.sections],
        )

    def _html(self, markdown: str) -> str:
        return IMAGE_SRC.sub(rf'src="{self._assets}/\2/\1"', _markdown.render(markdown))


def _releases(request: Request) -> Releases:
    container: Container = request.app.state.container
    return container.releases


ReleasesDep = Annotated[Releases, Depends(_releases)]
PagesDep = Annotated[ChangelogPages, Depends(ChangelogPages)]

router = APIRouter(tags=[TAG])


@router.get("/version", response_model=VersionView)
def get_version(releases: ReleasesDep):
    """The version this copy runs."""
    return VersionView(version=str(releases.installed.version))


@router.get("/updates", response_model=UpdateStatusView)
def check_for_updates(releases: ReleasesDep, pages: PagesDep, force: bool = False):
    """Whether a newer release is out and what it changes. Releases are asked at most once a day; `force` asks now."""
    status = releases.check.status(force=force)
    return UpdateStatusView(**status.model_dump(exclude={"entries"}), entries=pages.entries(status.entries))


@router.post("/update", status_code=202)
def start_update(request: Request, releases: ReleasesDep) -> None:
    """Starts updating this copy to the latest release; the app restarts on its way. Poll `GET /update/state`."""
    container: Container = request.app.state.container
    if container.refresh.progress.running:
        raise HTTPException(409, "Сейчас идёт обновление событий. Дождитесь его конца и обновите приложение")
    try:
        releases.runner.start()
    except UpdateAlreadyRunningError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/update/state", response_model=UpdateProgress)
def get_update_state(releases: ReleasesDep):
    """How the update started from the app is going."""
    return releases.runner.progress()


@router.get("/changelog", response_model=list[ChangelogEntryView])
def get_changelog(releases: ReleasesDep, pages: PagesDep):
    """Every release of the installed copy, newest first."""
    return pages.entries(releases.whats_new.all())


@router.get("/changelog/unseen", response_model=list[ChangelogEntryView])
def get_unseen_changelog(releases: ReleasesDep, pages: PagesDep):
    """Releases installed since the user last saw the changelog; empty on a fresh install."""
    return pages.entries(releases.whats_new.unseen())


@router.post("/changelog/seen", status_code=204)
def mark_changelog_seen(releases: ReleasesDep) -> None:
    """What's new was shown: it does not show again until the next update."""
    releases.whats_new.mark_seen()


@router.get(ASSETS_PATH + "/{version}/{path:path}")
def get_changelog_asset(version: str, path: str, releases: ReleasesDep) -> Response:
    """An image of a release's changelog."""
    requested = AppVersion.parse_or_none(version)
    content = releases.asset(requested, path) if requested else None
    if content is None:
        raise HTTPException(404, "Нет такой картинки")
    return Response(content=content, media_type=mimetypes.guess_type(path)[0] or "application/octet-stream")
