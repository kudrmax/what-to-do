from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import judge_same_titles
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.releases import (
    PROJECT_DIR,
    AppVersion,
    Changelog,
    InstalledRelease,
    ReleaseMemory,
    UpdateCheck,
    UpdateCommands,
    WhatsNew,
    is_changelog_asset,
)
from where_to_go.serving import AppWithInterface
from where_to_go.updating import UpdateFiles, UpdateRunner, UpdateState, UpdateStepStatus

CHANGELOG = """# Что нового

Что менялось в каждом релизе.

## 1.2.0 — 2026-11-20

Календарь недели.

### Календарь
Неделя целиком.
![](docs/images/changelog/1.2.0/week.png)

### Улучшения
- Быстрее.

## 1.1.0 — 2026-11-15

Мелочи.

### Исправлено
- Кнопка.

## 1.0.0 — 2026-11-10

Первый релиз.
"""


class FakeReleases:
    def __init__(self, latest: AppVersion | None, changelog: str = CHANGELOG) -> None:
        self.latest_version = latest
        self.changelog = changelog
        self.asks = 0

    def latest(self) -> AppVersion | None:
        self.asks += 1
        return self.latest_version

    def changelog_text(self, version: AppVersion) -> str | None:
        return self.changelog

    def asset(self, version: AppVersion, path: str) -> bytes | None:
        return b"png" if is_changelog_asset(path) else None


def project(tmp_path: Path, version: str = "1.0.0", changelog: str = CHANGELOG) -> Path:
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n')
    (folder / "CHANGELOG.md").write_text(changelog)
    return folder


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 21, 12, 0)

    def __call__(self) -> datetime:
        return self.now


def test_versions_compare_as_numbers():
    assert AppVersion.parse("v1.10.0") > AppVersion.parse("1.9.3")
    assert AppVersion.parse_or_none("next") is None


def test_changelog_reads_entries_and_sections():
    newest, middle, first = Changelog.parse(CHANGELOG)
    assert (newest.version, newest.released_on, newest.summary) == ("1.2.0", date(2026, 11, 20), "Календарь недели.")
    assert [section.title for section in newest.sections] == ["Календарь", "Улучшения"]
    assert newest.sections[1].body_markdown == "- Быстрее."
    assert first.sections == []
    assert [entry.version for entry in Changelog.between(CHANGELOG, AppVersion(1, 0, 0), AppVersion(1, 2, 0))] == ["1.2.0", "1.1.0"]


def test_changelog_refuses_a_malformed_heading():
    with pytest.raises(ValueError):
        Changelog.parse("## next - soon\n")


def test_the_project_changelog_parses_and_matches_the_version():
    entries = Changelog.parse((PROJECT_DIR / "CHANGELOG.md").read_text(encoding="utf-8"))
    installed = InstalledRelease(PROJECT_DIR).version
    assert not entries or entries[0].app_version == installed


def test_only_changelog_images_leave_a_release():
    assert is_changelog_asset("docs/images/changelog/1.2.0/week.png")
    assert not is_changelog_asset("docs/images/changelog/../../../.env")
    assert not is_changelog_asset("/etc/passwd")
    assert not is_changelog_asset("pyproject.toml")


def check(tmp_path, source, clock):
    folder = project(tmp_path)
    memory = ReleaseMemory(tmp_path / "data" / "releases.json")
    return UpdateCheck(InstalledRelease(folder), source, memory, UpdateCommands(folder), now=clock)


def test_a_newer_release_brings_its_changes(tmp_path):
    status = check(tmp_path, FakeReleases(AppVersion(1, 2, 0)), Clock()).status(force=False)
    assert (status.current, status.latest, status.available) == ("1.0.0", "1.2.0", True)
    assert [entry.version for entry in status.entries] == ["1.2.0", "1.1.0"]
    assert status.update_command.endswith("&& make update")


def test_releases_are_asked_once_a_day_unless_forced(tmp_path):
    source, clock = FakeReleases(AppVersion(1, 1, 0)), Clock()
    updates = check(tmp_path, source, clock)
    updates.status(force=False)
    source.latest_version = AppVersion(1, 2, 0)
    assert updates.status(force=False).latest == "1.1.0"
    assert updates.status(force=True).latest == "1.2.0"
    clock.now += timedelta(days=1, minutes=1)
    updates.status(force=False)
    assert source.asks == 3


def test_a_failed_ask_waits_an_hour_and_keeps_the_last_answer(tmp_path):
    source, clock = FakeReleases(AppVersion(1, 1, 0)), Clock()
    updates = check(tmp_path, source, clock)
    updates.status(force=False)
    clock.now += timedelta(days=2)
    source.latest_version = None
    assert updates.status(force=True).check_failed
    failed = updates.status(force=False)
    assert (failed.latest, failed.check_failed, source.asks) == ("1.1.0", False, 2)


def test_whats_new_shows_releases_since_the_last_seen(tmp_path):
    memory = ReleaseMemory(tmp_path / "releases.json")
    assert WhatsNew(InstalledRelease(project(tmp_path, "1.0.0")), memory).unseen() == []
    (tmp_path / "project").rename(tmp_path / "old")
    updated = WhatsNew(InstalledRelease(project(tmp_path, "1.2.0")), memory)
    assert [entry.version for entry in updated.unseen()] == ["1.2.0", "1.1.0"]
    updated.mark_seen()
    assert updated.unseen() == []


def test_update_state_comes_from_the_script_files(tmp_path):
    files = UpdateFiles(tmp_path)
    runner = UpdateRunner(tmp_path)
    assert runner.progress().state is UpdateState.IDLE
    files.write(UpdateFiles.PROGRESS, "done\tСкачиваем v1.2.0\ncurrent\tУстанавливаем v1.2.0\n")
    files.write(UpdateFiles.STATE, "done")
    progress = runner.progress()
    assert progress.state is UpdateState.DONE
    assert [step.status for step in progress.steps] == [UpdateStepStatus.DONE, UpdateStepStatus.CURRENT]


def test_an_update_whose_script_died_has_failed(tmp_path):
    files = UpdateFiles(tmp_path)
    files.write(UpdateFiles.STATE, "running")
    files.write(UpdateFiles.PID, "999999")
    files.write(UpdateFiles.ERROR, "'make up' failed.")
    files.write(UpdateFiles.LOG, "old run\n=== make update 2026\nnpm \x1b[31mERR\x1b[0m\n")
    progress = UpdateRunner(tmp_path).progress()
    assert progress.state is UpdateState.FAILED
    assert progress.log_tail == "'make up' failed.\n\n=== make update 2026\nnpm ERR"
    assert files.state() is UpdateState.FAILED


@pytest.fixture
def client(tmp_path):
    folder = project(tmp_path)
    image = folder / "docs/images/changelog/1.0.0/first.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"installed png")
    container = lambda: Container.build(  # noqa: E731
        tmp_path / "data", matching_llm=judge_same_titles(), project_dir=folder, release_source=FakeReleases(AppVersion(1, 2, 0))
    )
    with TestClient(create_app(container)) as test_client:
        yield test_client


def test_api_tells_the_version_and_the_update(client):
    assert client.get("/version").json() == {"version": "1.0.0"}
    status = client.get("/updates").json()
    assert status["available"] and status["latest"] == "1.2.0"
    calendar = status["entries"][0]["sections"][0]
    assert calendar["title"] == "Календарь"
    assert '<img src="/changelog/assets/1.2.0/docs/images/changelog/1.2.0/week.png"' in calendar["html"]
    assert client.get("/changelog/assets/1.2.0/docs/images/changelog/1.2.0/week.png").content == b"png"
    assert client.get("/changelog/assets/1.0.0/docs/images/changelog/1.0.0/first.png").content == b"installed png"
    assert client.get("/changelog/assets/1.2.0/pyproject.toml").status_code == 404


def test_api_whats_new_shows_once(client):
    assert [entry["version"] for entry in client.get("/changelog").json()] == ["1.2.0", "1.1.0", "1.0.0"]
    assert client.get("/changelog/unseen").json() == []
    assert client.post("/changelog/seen").status_code == 204
    assert client.get("/update/state").json() == {"state": "idle", "log_tail": "", "steps": []}


def test_images_point_under_the_interface_api(tmp_path):
    folder = project(tmp_path)
    interface = tmp_path / "dist"
    (interface / "assets").mkdir(parents=True)
    (interface / "index.html").write_text("<html></html>")
    api = create_app(lambda: Container.build(tmp_path / "data", matching_llm=judge_same_titles(), project_dir=folder, release_source=FakeReleases(AppVersion(1, 2, 0))))
    with TestClient(AppWithInterface.build(api, interface)) as test_client:
        html = test_client.get("/api/updates").json()["entries"][0]["sections"][0]["html"]
        assert 'src="/api/changelog/assets/1.2.0/' in html
