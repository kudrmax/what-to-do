"""Updates the app installed from a disk image: downloads the new release's image from GitHub, copies its
app next to the installed one while the app still runs, then stops the app, swaps the two bundles and
starts the new version. The window notices the new bundle and offers to restart into it.

The old bundle moves away while this process still runs from it, so everything this module needs after
the swap is imported before it."""
from __future__ import annotations

import hashlib
import os
import plistlib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from send2trash import send2trash

from where_to_go.about import VERSION
from where_to_go.launcher.bundle import AppBundle
from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.github_releases import GitHubReleaseFeed, PublishedImage, ReleaseFeedError
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.spec import ServerSpec
from where_to_go.launcher.update_journal import UpdateWord
from where_to_go.launcher.updater import CHECK, INSTALL, START, UpdateFailedError, UpdateLog, Updater

CHUNK = 1 << 20
PROGRESS_STEP_PERCENT = 5
DOWNLOAD_TIMEOUT_S = 60
NOT_MOVED = "Move What To Do to the Applications folder, open it from there and update again."


class DiskImageInstaller:
    """Gets the new app out of a release's disk image and puts it in place of the installed one."""

    def __init__(self, log: UpdateLog, run: Callable[[list[str]], int] | None = None, trash: Callable[[str], None] = send2trash) -> None:
        self._log = log
        self._run = run or (lambda command: log.run(command, Path("/")))
        self._trash = trash

    def download(self, image: PublishedImage, folder: Path, progress: Callable[[int], None]) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / Path(image.url).name
        partial = target.with_name(target.name + ".part")
        digest = hashlib.sha256()
        try:
            request = urllib.request.Request(image.url, headers={"User-Agent": "what-to-do-app"})
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response, partial.open("wb") as file:  # noqa: S310
                total = int(response.headers.get("Content-Length") or image.size or 0)
                done = 0
                while chunk := response.read(CHUNK):
                    file.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if total:
                        progress(min(100, done * 100 // total))
        except (OSError, urllib.error.URLError) as error:
            partial.unlink(missing_ok=True)
            raise UpdateFailedError(f"Couldn't download the new version: {error}") from error
        if image.sha256 and digest.hexdigest() != image.sha256:
            partial.unlink(missing_ok=True)
            raise UpdateFailedError("The downloaded disk image is damaged (its checksum doesn't match). Try updating again.")
        partial.replace(target)
        return target

    def stage(self, disk_image: Path, installed: AppBundle, version: str) -> Path:
        """Copies the app out of the image next to the installed one, on the same disk, so the swap is a rename."""
        staged = installed.app.with_name(f".{installed.app.name}.{version}.new")
        self._discard(staged)
        mount = disk_image.with_suffix(".mount")
        mount.mkdir(parents=True, exist_ok=True)
        if self._run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount), str(disk_image)]) != 0:
            raise UpdateFailedError("Couldn't open the downloaded disk image.")
        try:
            apps = sorted(mount.glob("*.app"))
            if len(apps) != 1:
                raise UpdateFailedError("The downloaded disk image has no app in it.")
            if self._run(["ditto", str(apps[0]), str(staged)]) != 0:
                raise UpdateFailedError(f"Couldn't copy the new version into {installed.app.parent}.")
        finally:
            if self._run(["hdiutil", "detach", str(mount)]) != 0:
                self._run(["hdiutil", "detach", "-force", str(mount)])
            if mount.is_dir() and not any(mount.iterdir()):
                mount.rmdir()
        disk_image.unlink(missing_ok=True)
        self._check(staged, installed.arch, version)
        return staged

    def swap(self, staged: Path, installed: Path) -> None:
        previous = installed.with_name(f".{installed.name}.previous")
        self._discard(previous)
        os.rename(installed, previous)
        try:
            os.rename(staged, installed)
        except OSError:
            os.rename(previous, installed)
            raise
        self._discard(previous)

    def _check(self, staged: Path, arch: str, version: str) -> None:
        try:
            with (staged / "Contents" / "Info.plist").open("rb") as file:
                found = plistlib.load(file).get("CFBundleShortVersionString")
            marker = AppBundle.current(staged / "Contents" / "Resources" / "python")
        except (OSError, plistlib.InvalidFileException, ValueError):
            found, marker = None, None
        if found != version or marker is None or marker.arch != arch:
            self._discard(staged)
            raise UpdateFailedError(f"The downloaded disk image doesn't hold What To Do {version} for this Mac.")
        if self._run(["codesign", "--verify", str(staged)]) != 0:
            self._discard(staged)
            raise UpdateFailedError("The new version's signature is broken. Try updating again.")

    def _discard(self, path: Path) -> None:
        if path.exists():
            self._trash(str(path))


class BundleUpdater(Updater):
    """The Update button of the app installed from a disk image; git copies update with `Updater`."""

    def __init__(
        self,
        paths: ProjectPaths,
        config: InstanceConfig,
        log: UpdateLog,
        bundle: AppBundle,
        feed: GitHubReleaseFeed | None = None,
        installer: DiskImageInstaller | None = None,
        current_version: str = VERSION,
        **options: object,
    ) -> None:
        super().__init__(paths, config, log, **options)  # type: ignore[arg-type]
        self._bundle = bundle
        self._feed = feed or GitHubReleaseFeed(bundle.image)
        self._installer = installer or DiskImageInstaller(log)
        self._current = tuple(int(part) for part in current_version.split("."))
        self._shown_percent = -PROGRESS_STEP_PERCENT

    def _update(self) -> None:
        self._stages.begin(CHECK, INSTALL, START)
        self._refuse_where_unwritable()
        try:
            image = self._feed.latest()
        except ReleaseFeedError as error:
            self._log.say(str(error))
            raise UpdateFailedError("Couldn't reach GitHub. Check your internet connection and try updating again.") from error
        if image is None or image.version <= self._current:
            self._log.say(f"Already up to date ({VERSION}).")
            return self._nothing_to_do()

        self._log.say(f"Updating to {image.tag}...")
        self._stages.rename(0, f"Downloading {image.tag}")
        self._stages.rename(1, f"Installing {image.tag}")
        disk_image = self._installer.download(image, self._paths.writable / "updates", lambda percent: self._downloaded(image, percent))
        self._stages.rename(0, f"Downloading {image.tag}")
        self._stages.advance()
        staged = self._installer.stage(disk_image, self._bundle, image.version_text)

        servers = self._running_servers()
        self._call_cli(["down"], "Couldn't stop the app.")
        for server in servers:
            self._status.start(server.port)
        try:
            self._installer.swap(staged, self._bundle.app)
        except OSError as error:
            self._log.say(f"Couldn't replace {self._bundle.app}: {error}")
            self._restart_old(servers)
            raise UpdateFailedError(f"Couldn't replace the app in {self._bundle.app.parent}. {NOT_MOVED}") from error
        self._stages.advance()

        for server in servers:
            self._call_cli(["up", *server.arguments()], "Couldn't start the new version.")
        self._stages.advance()
        self._log.say(f"Updated to {image.tag}.")
        self._finish(UpdateWord.DONE)

    def _restart_old(self, servers: list[ServerSpec]) -> None:
        for server in servers:
            self._log.run([*self._cli, "up", *server.arguments()], self._paths.root)

    def _downloaded(self, image: PublishedImage, percent: int) -> None:
        if percent - self._shown_percent < PROGRESS_STEP_PERCENT and percent < 100:
            return
        self._shown_percent = percent
        self._stages.rename(0, f"Downloading {image.tag}: {percent}%")

    def _refuse_where_unwritable(self) -> None:
        """An app opened from the disk image or from Downloads runs from a read-only copy macOS made of it."""
        app = self._bundle.app
        if "AppTranslocation" in app.parts or app.parts[1:2] == ("Volumes",) or not os.access(app.parent, os.W_OK):
            raise UpdateFailedError(f"What To Do can't update itself where it is ({app.parent}). {NOT_MOVED}")

