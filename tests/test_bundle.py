"""The app installed from the macOS disk image: where it reads and writes, the releases it learns from
GitHub, and its update, which swaps the whole app bundle for the one from the new release's image."""

from __future__ import annotations

import hashlib
import json
import plistlib
import shutil
import sys
from pathlib import Path

import pytest

from tests.test_updater import FAKE_CLI, STATUS_SERVER, free_port
from where_to_go.launcher.bundle import AppBundle, DiskImageName
from where_to_go.launcher.bundle_updater import BundleUpdater, DiskImageInstaller
from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.github_releases import GitHubReleaseFeed, PublishedImage, ReleaseFeedError
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.updater import UpdateLog
from where_to_go.releases import RELEASES_PAGE, AppVersion, GitHubReleases, InstalledRelease, ReleaseMemory, UpdateCheck, UpdateCommands
from where_to_go.updating import UpdateFiles


def make_app(folder: Path, version: str, arch: str = "arm64") -> Path:
    app = folder / "What To Do.app"
    project = app / "Contents" / "Resources" / "project"
    project.mkdir(parents=True)
    (project / "bundle.json").write_text(json.dumps({"arch": arch, "version": version}), encoding="utf-8")
    (app / "Contents" / "Resources" / "python" / "bin").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as plist:
        plistlib.dump({"CFBundleShortVersionString": version}, plist)
    return app


def release(tag: str, *assets: str, draft: bool = False, prerelease: bool = False) -> dict[str, object]:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": name, "browser_download_url": f"https://example.com/{name}", "size": 10, "digest": "sha256:ab"} for name in assets],
    }


def feed_answering(releases: object, files: dict[str, bytes] | None = None) -> GitHubReleaseFeed:
    def get(url: str) -> bytes:
        if "/releases?" in url:
            return json.dumps(releases).encode()
        for suffix, content in (files or {}).items():
            if url.endswith(suffix):
                return content
        raise ReleaseFeedError(f"{url}: 404")

    return GitHubReleaseFeed(DiskImageName("arm64"), environ={}, get=get)


def test_a_python_inside_the_bundle_knows_its_bundle(tmp_path: Path) -> None:
    app = make_app(tmp_path, "1.2.0", arch="x86_64")

    bundle = AppBundle.current(app / "Contents" / "Resources" / "python")

    assert bundle == AppBundle(app=app, arch="x86_64")
    assert bundle.project == app / "Contents" / "Resources" / "project"
    assert bundle.python == app / "Contents" / "Resources" / "python" / "bin" / "python3"


def test_a_git_copy_is_no_bundle(tmp_path: Path) -> None:
    assert AppBundle.current(tmp_path / ".venv") is None


def test_the_bundle_writes_only_to_its_state_folder(tmp_path: Path) -> None:
    bundle = AppBundle(app=tmp_path / "What To Do.app", arch="arm64")
    paths = ProjectPaths(bundle.project, state=tmp_path / "state", bundle=bundle)

    assert paths.pids == tmp_path / "state" / ".pids"
    assert paths.logs == tmp_path / "state" / ".logs"
    assert paths.env_file == tmp_path / "state" / ".env"
    assert paths.dist == bundle.project / "frontend" / "dist"


def test_the_state_folder_is_in_application_support_unless_named(tmp_path: Path) -> None:
    assert AppBundle.state_dir({}) == Path.home() / "Library" / "Application Support" / "What To Do"
    assert AppBundle.state_dir({"WHERE_TO_GO_STATE_DIR": str(tmp_path)}) == tmp_path.resolve()


def test_disk_images_are_named_for_the_kind_of_mac() -> None:
    assert DiskImageName("arm64").of("1.19.0") == "What-To-Do-1.19.0-Apple-Silicon.dmg"
    assert DiskImageName("x86_64").of("1.19.0") == "What-To-Do-1.19.0-Intel.dmg"
    with pytest.raises(ValueError):
        DiskImageName("ppc")


def test_the_latest_release_is_the_newest_with_an_image_for_this_mac() -> None:
    feed = feed_answering([
        release("v1.21.0", "What-To-Do-1.21.0-Intel.dmg"),
        release("v1.22.0", "What-To-Do-1.22.0-Apple-Silicon.dmg", draft=True),
        release("v1.23.0", "What-To-Do-1.23.0-Apple-Silicon.dmg", prerelease=True),
        release("v1.9.0", "What-To-Do-1.9.0-Apple-Silicon.dmg"),
        release("v1.20.0", "What-To-Do-1.20.0-Apple-Silicon.dmg"),
        release("nightly", "What-To-Do-nightly-Apple-Silicon.dmg"),
    ])

    latest = feed.latest()

    assert latest == PublishedImage((1, 20, 0), "https://example.com/What-To-Do-1.20.0-Apple-Silicon.dmg", 10, "ab")
    assert latest is not None and latest.tag == "v1.20.0"


def test_no_release_with_an_image_yet_means_nothing_newer() -> None:
    assert feed_answering([release("v2.0.0")]).latest() is None


def test_garbage_from_github_is_an_error() -> None:
    with pytest.raises(ReleaseFeedError):
        feed_answering({"message": "rate limited"}).latest()


def test_the_page_learns_releases_and_their_changelog_from_github() -> None:
    releases = GitHubReleases(feed_answering([release("v1.20.0", "What-To-Do-1.20.0-Apple-Silicon.dmg")], {"/v1.20.0/CHANGELOG.md": b"## 1.20.0"}), AppVersion(1, 0, 0))

    assert releases.latest() == AppVersion(1, 20, 0)
    assert releases.changelog_text(AppVersion(1, 20, 0)) == "## 1.20.0"
    assert releases.asset(AppVersion(1, 20, 0), "../secret") is None
    assert releases.asset(AppVersion(1, 20, 0), "docs/images/changelog/1.20.0/missing.png") is None


def test_an_unreachable_github_leaves_the_latest_unknown() -> None:
    def offline(url: str) -> bytes:
        raise ReleaseFeedError("offline")

    assert GitHubReleases(GitHubReleaseFeed(DiskImageName("arm64"), environ={}, get=offline), AppVersion(1, 0, 0)).latest() is None


def test_until_a_release_has_its_image_the_installed_version_is_the_latest() -> None:
    assert GitHubReleases(feed_answering([release("v1.20.0")]), AppVersion(1, 19, 0)).latest() == AppVersion(1, 19, 0)


def test_the_bundle_has_no_terminal_commands_and_points_to_the_download_page(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")

    class Source:
        def latest(self) -> AppVersion:
            return AppVersion(1, 1, 0)

        def changelog_text(self, version: AppVersion) -> None:
            return None

        def asset(self, version: AppVersion, path: str) -> None:
            return None

    memory = ReleaseMemory(tmp_path / "releases.json")
    bundled = UpdateCheck(InstalledRelease(project), Source(), memory, None).status(force=True)
    git_copy = UpdateCheck(InstalledRelease(project), Source(), memory, UpdateCommands(project, windows=False)).status(force=True)

    assert (bundled.restart_command, bundled.update_command, bundled.download_page) == (None, None, RELEASES_PAGE)
    assert git_copy.update_command is not None and git_copy.download_page is None


class FakeDiskTools:
    """Stands in for hdiutil, ditto and codesign: the "disk image" is a folder holding the app."""

    def __init__(self, image_contents: Path) -> None:
        self.image_contents = image_contents
        self.calls: list[str] = []

    def __call__(self, command: list[str]) -> int:
        self.calls.append(command[0] + " " + command[1])
        if command[:2] == ["hdiutil", "attach"]:
            mount = Path(command[command.index("-mountpoint") + 1])
            shutil.copytree(self.image_contents, mount, dirs_exist_ok=True)
        elif command[0] == "ditto":
            shutil.copytree(command[1], command[2], symlinks=True)
        return 0


class Published:
    """A release on "GitHub": its disk image is a file served by a file:// address."""

    def __init__(self, tmp_path: Path, version: str, arch: str = "arm64") -> None:
        self.version = version
        self.contents = tmp_path / f"image-{version}"
        make_app(self.contents, version, arch)
        self.file = tmp_path / "downloads" / DiskImageName("arm64").of(version)
        self.file.parent.mkdir(exist_ok=True)
        self.file.write_bytes(b"disk image " + version.encode())
        self.sha256 = hashlib.sha256(self.file.read_bytes()).hexdigest()

    def image(self, sha256: str | None = None) -> PublishedImage:
        return PublishedImage(tuple(int(part) for part in self.version.split(".")), self.file.as_uri(), self.file.stat().st_size, sha256 or self.sha256)  # type: ignore[arg-type]


class FixedFeed:
    def __init__(self, image: PublishedImage | None) -> None:
        self._image = image

    def latest(self) -> PublishedImage | None:
        return self._image


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, int]:
    """An installed 1.0.0 app with one server, its state folder and the fake command line's switches."""
    apps = tmp_path / "Applications"
    app = make_app(apps, "1.0.0")
    state = tmp_path / "state"
    (state / "scripts").mkdir(parents=True)
    shutil.copy(STATUS_SERVER, state / "scripts" / STATUS_SERVER.name)
    (state / "VERSION").write_text("new", encoding="utf-8")
    flags = tmp_path / "flags"
    flags.mkdir()
    port = free_port()
    server = {"port": port, "data_dir": str(tmp_path / "data"), "ui": str(app / "Contents" / "Resources" / "project" / "frontend" / "dist"), "instance": "prod"}
    (flags / "servers.json").write_text(json.dumps({"servers": [server]}), encoding="utf-8")
    monkeypatch.setenv("CALLS", str(tmp_path / "calls.txt"))
    monkeypatch.setenv("FLAGS", str(flags))
    return app, state, port


def updater(app: Path, state: Path, port: int, feed: FixedFeed, disk_tools: FakeDiskTools, trash: list[str]) -> BundleUpdater:
    bundle = AppBundle(app=app, arch="arm64")
    paths = ProjectPaths(state, state=state, bundle=bundle)
    config = InstanceConfig(port=port, data_dir=state / "data", instance="prod", menu_bar_icon=False)
    log = UpdateLog(paths.update_log, echo=None)
    trash_folder = state.parent / "Trash"

    def move_to_trash(path: str) -> None:
        trash.append(path)
        trash_folder.mkdir(exist_ok=True)
        shutil.move(path, trash_folder / f"{len(trash)}-{Path(path).name}")

    installer = DiskImageInstaller(log, run=disk_tools, trash=move_to_trash)
    return BundleUpdater(paths, config, log, bundle, feed=feed, installer=installer, current_version="1.0.0", cli=[sys.executable, FAKE_CLI])  # type: ignore[arg-type]


def version_of(app: Path) -> str:
    with (app / "Contents" / "Info.plist").open("rb") as plist:
        return str(plistlib.load(plist)["CFBundleShortVersionString"])


def test_the_update_swaps_the_app_for_the_new_release_and_restarts_what_ran(installed: tuple[Path, Path, int], tmp_path: Path) -> None:
    app, state, port = installed
    published = Published(tmp_path, "1.1.0")
    disk_tools = FakeDiskTools(published.contents)
    trash: list[str] = []

    assert updater(app, state, port, FixedFeed(published.image()), disk_tools, trash).run() == 0, (state / ".logs" / "update.log").read_text()

    assert version_of(app) == "1.1.0"
    assert not list(app.parent.glob(".*"))
    assert trash == [str(app.with_name(".What To Do.app.previous"))]
    assert (tmp_path / "calls.txt").read_text(encoding="utf-8").splitlines() == ["down", "up new"]
    assert [call.split()[0] for call in disk_tools.calls] == ["hdiutil", "ditto", "hdiutil", "codesign"]
    assert UpdateFiles(state).state().value == "done"
    assert [step.title for step in UpdateFiles(state).steps()] == ["Downloading v1.1.0", "Installing v1.1.0", "Starting the new version"]


def test_nothing_newer_changes_nothing(installed: tuple[Path, Path, int], tmp_path: Path) -> None:
    app, state, port = installed
    disk_tools = FakeDiskTools(tmp_path)

    assert updater(app, state, port, FixedFeed(None), disk_tools, []).run() == 0

    assert version_of(app) == "1.0.0"
    assert disk_tools.calls == []
    assert not (tmp_path / "calls.txt").exists()


def test_a_damaged_download_leaves_the_app_as_it_was(installed: tuple[Path, Path, int], tmp_path: Path) -> None:
    app, state, port = installed
    published = Published(tmp_path, "1.1.0")

    assert updater(app, state, port, FixedFeed(published.image(sha256="0" * 64)), FakeDiskTools(published.contents), []).run() == 1

    assert version_of(app) == "1.0.0"
    assert "damaged" in UpdateFiles(state).read(UpdateFiles.ERROR)
    assert not (tmp_path / "calls.txt").exists()


def test_an_image_of_another_version_is_refused_before_the_app_stops(installed: tuple[Path, Path, int], tmp_path: Path) -> None:
    app, state, port = installed
    published = Published(tmp_path, "1.1.0")
    shutil.rmtree(published.contents)
    make_app(published.contents, "1.0.5")
    trash: list[str] = []

    assert updater(app, state, port, FixedFeed(published.image()), FakeDiskTools(published.contents), trash).run() == 1

    assert version_of(app) == "1.0.0"
    assert "doesn't hold What To Do 1.1.0" in UpdateFiles(state).read(UpdateFiles.ERROR)
    assert trash == [str(app.with_name(".What To Do.app.1.1.0.new"))]
    assert not (tmp_path / "calls.txt").exists()


def test_an_app_running_from_the_disk_image_says_to_move_it_first(installed: tuple[Path, Path, int], tmp_path: Path) -> None:
    _, state, port = installed
    translocated = make_app(tmp_path / "private" / "var" / "folders" / "AppTranslocation" / "X" / "d", "1.0.0")
    published = Published(tmp_path, "1.1.0")

    assert updater(translocated, state, port, FixedFeed(published.image()), FakeDiskTools(published.contents), []).run() == 1

    assert "Move What To Do to the Applications folder" in UpdateFiles(state).read(UpdateFiles.ERROR)
