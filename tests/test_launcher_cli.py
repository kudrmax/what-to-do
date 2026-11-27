"""The settings of a copy, its logs, and taking the app off the computer."""

from __future__ import annotations

import io
import plistlib
import sys
from pathlib import Path

import pytest

from tests.helpers import FakeClaude
from where_to_go.installed_cli import CliStatus
from where_to_go.launcher.cli import NOT_RUNNING_EXIT, Cli
from where_to_go.launcher.config import DEFAULT_PORT, ConfigError, InstanceConfig
from where_to_go.launcher.logs import LogFollower
from where_to_go.launcher.macos_apps import MacApps
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.uninstall import Uninstaller, UninstallRefusedError


def copy_at(tmp_path: Path, env: str | None = None, worktree: bool = False) -> ProjectPaths:
    root = tmp_path / "copy"
    root.mkdir()
    if worktree:
        (root / ".git").write_text("gitdir: /somewhere/.git/worktrees/copy\n", encoding="utf-8")
    else:
        (root / ".git").mkdir()
    if env is not None:
        (root / ".env").write_text(env, encoding="utf-8")
    return ProjectPaths(root)


def test_everyone_gets_the_same_defaults(tmp_path: Path) -> None:
    config = InstanceConfig.load(copy_at(tmp_path), environ={})

    assert config.port == DEFAULT_PORT
    assert config.data_dir == InstanceConfig.default_data_dir()
    assert config.data_dir.name == "where-to-go"
    assert config.instance == "prod"
    assert not config.menu_bar_icon


def test_the_prod_copy_with_an_empty_data_dir_keeps_the_default_folder(tmp_path: Path) -> None:
    paths = copy_at(tmp_path, "INSTANCE_ENV_NAME=prod\nPORT=18765\nDATA_DIR=\nMENU_BAR_ICON=1\n")

    config = InstanceConfig.load(paths, environ={})

    assert (config.port, config.data_dir, config.instance, config.menu_bar_icon) == (18765, InstanceConfig.default_data_dir(), "prod", True)


def test_a_dev_copy_keeps_its_data_inside(tmp_path: Path) -> None:
    paths = copy_at(tmp_path, "# Label\nINSTANCE_ENV_NAME=dev\nPORT=18766  # the dev port\nDATA_DIR=./data\n")

    config = InstanceConfig.load(paths, environ={})

    assert (config.port, config.data_dir, config.instance) == (18766, (paths.root / "data").resolve(), "dev")


def test_quoted_values_and_exports_are_read(tmp_path: Path) -> None:
    paths = copy_at(tmp_path, 'export PORT="18800"\nDATA_DIR=\'~/wtd data\'\n')

    config = InstanceConfig.load(paths, environ={})

    assert config.port == 18800
    assert config.data_dir == (Path.home() / "wtd data").resolve()


def test_the_environment_overrides_the_env_file(tmp_path: Path) -> None:
    paths = copy_at(tmp_path, "PORT=18766\nDATA_DIR=./data\n")
    environ = {"WHERE_TO_GO_PORT": "18900", "WHERE_TO_GO_DATA_DIR": str(tmp_path / "elsewhere"), "WHERE_TO_GO_INSTANCE": "ci"}

    config = InstanceConfig.load(paths, environ=environ)

    assert (config.port, config.data_dir, config.instance) == (18900, (tmp_path / "elsewhere").resolve(), "ci")


def test_a_git_worktree_never_opens_the_real_data_by_default(tmp_path: Path) -> None:
    paths = copy_at(tmp_path, worktree=True)

    config = InstanceConfig.load(paths, environ={})

    assert config.data_dir == paths.root / "data"
    assert config.instance == "dev"


@pytest.mark.parametrize("port", ["eighty", "0", "70000"])
def test_a_wrong_port_is_refused_with_its_value(tmp_path: Path, port: str) -> None:
    with pytest.raises(ConfigError, match=port):
        InstanceConfig.load(copy_at(tmp_path, f"PORT={port}\n"), environ={})


def test_the_example_env_file_changes_nothing(tmp_path: Path) -> None:
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    with_example = tmp_path / "with-example"
    with_example.mkdir()

    assert InstanceConfig.load(copy_at(with_example, example), environ={}) == InstanceConfig.load(copy_at(tmp_path), environ={})


def test_logs_show_both_streams_marked_and_follow_new_lines(tmp_path: Path) -> None:
    app_log, update_log = tmp_path / "app.log", tmp_path / "update.log"
    app_log.write_text("one\ntwo\nthree\n", encoding="utf-8")
    said: list[str] = []
    follower = LogFollower([("app", app_log), ("update", update_log)], said.append)

    follower.run(lines=2, follow=False)
    update_log.write_text("=== update\nhalf", encoding="utf-8")
    new = follower._new_lines(follower._files[1])

    assert said == ["app    | two", "app    | three"]
    assert new == ["=== update"]


class FakeControl:
    def __init__(self) -> None:
        self.downs = 0

    def down(self) -> list[object]:
        self.downs += 1
        return []


class Trash:
    def __init__(self, fail: bool = False) -> None:
        self.items: list[str] = []
        self._fail = fail

    def __call__(self, path: str) -> None:
        if self._fail:
            raise PermissionError("the trash is not available")
        self.items.append(path)


def install_app(apps_dir: Path, name: str, project_dir: Path) -> Path:
    app = apps_dir / f"{name}.app"
    (app / "Contents").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as plist:
        plistlib.dump({"WTGProjectDir": str(project_dir)}, plist)
    return app


@pytest.fixture
def installed(tmp_path: Path) -> tuple[ProjectPaths, Path, Path]:
    paths = copy_at(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "where-to-go.sqlite3").write_text("", encoding="utf-8")
    apps = tmp_path / "Applications"
    install_app(apps, "What To Do", paths.root)
    install_app(apps, "What To Do Dev", tmp_path / "another-copy")
    return paths, data, apps


def test_uninstall_stops_the_app_and_moves_its_app_and_data_to_the_trash(installed: tuple[ProjectPaths, Path, Path]) -> None:
    paths, data, apps = installed
    control, trash = FakeControl(), Trash()

    report = Uninstaller(paths, control, data, MacApps(apps), trash).run(delete_data=True)

    assert control.downs == 1
    assert trash.items == [str(apps / "What To Do.app"), str(data)]
    assert report.removed == [apps / "What To Do.app", data]


def test_uninstall_can_keep_the_data(installed: tuple[ProjectPaths, Path, Path]) -> None:
    paths, data, apps = installed
    trash = Trash()

    report = Uninstaller(paths, FakeControl(), data, MacApps(apps), trash).run(delete_data=False)

    assert str(data) not in trash.items
    assert report.kept == [data]


def test_uninstall_never_takes_a_folder_that_holds_more_than_the_data(installed: tuple[ProjectPaths, Path, Path]) -> None:
    paths, _, apps = installed
    control, trash = FakeControl(), Trash()

    with pytest.raises(UninstallRefusedError):
        Uninstaller(paths, control, Path.home(), MacApps(apps), trash).run(delete_data=True)
    with pytest.raises(UninstallRefusedError):
        Uninstaller(paths, control, paths.root, MacApps(apps), trash).run(delete_data=True)

    assert trash.items == []
    assert control.downs == 0


def test_what_could_not_go_to_the_trash_is_reported(installed: tuple[ProjectPaths, Path, Path]) -> None:
    paths, data, apps = installed

    report = Uninstaller(paths, FakeControl(), data, MacApps(apps), Trash(fail=True)).run(delete_data=True)

    assert [path for path, _ in report.failed] == [apps / "What To Do.app", data]
    assert report.removed == []


def test_uninstall_asks_before_it_does_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = copy_at(tmp_path)
    config = InstanceConfig(port=DEFAULT_PORT, data_dir=tmp_path / "data", instance="prod", menu_bar_icon=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert Cli(paths, config, out=lambda _: None).run(["uninstall"]) == 2


def test_uninstall_keeps_the_data_unless_the_user_says_yes(installed: tuple[ProjectPaths, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    paths, data, _ = installed
    config = InstanceConfig(port=1, data_dir=data, instance="prod", menu_bar_icon=False)
    answers = iter(["y", ""])
    monkeypatch.setattr(sys, "stdin", type("Terminal", (io.StringIO,), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    trashed: list[str] = []
    monkeypatch.setattr("where_to_go.launcher.uninstall.send2trash", trashed.append)
    said: list[str] = []

    assert Cli(paths, config, out=said.append).run(["uninstall"]) == 0

    assert str(data) not in trashed
    assert f"Kept your data: {data}" in said
    assert any(line.startswith("\nLast step: delete the folder") for line in said)


def test_status_of_a_stopped_copy_says_how_to_start_it(tmp_path: Path) -> None:
    paths = copy_at(tmp_path)
    config = InstanceConfig(port=1, data_dir=tmp_path / "data", instance="prod", menu_bar_icon=False)
    said: list[str] = []

    assert Cli(paths, config, out=said.append).run(["status"]) == NOT_RUNNING_EXIT
    assert said[0] == "What To Do is not running."
    assert any("where-to-go up" in line for line in said)


def test_the_app_from_the_disk_image_starts_on_a_rarely_used_port(tmp_path: Path) -> None:
    from where_to_go.launcher.bundle import AppBundle
    bundle = AppBundle(app=tmp_path / "What To Do.app", arch="arm64")
    paths = ProjectPaths(bundle.project, state=tmp_path / "state", bundle=bundle)

    config = InstanceConfig.load(paths, environ={})

    assert config.port == DEFAULT_PORT == 48765
    assert not config.port_fixed


def test_the_port_command_prints_only_the_port_and_moves_off_a_taken_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import socket

    paths = copy_at(tmp_path)
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        taken = holder.getsockname()[1]
        config = InstanceConfig(port=taken, data_dir=tmp_path / "data", instance="prod", menu_bar_icon=False, port_fixed=False)
        printed: list[str] = []

        assert Cli(paths, config, out=printed.append).run(["port"]) == 0

    [port] = printed
    assert int(port) != taken
    assert f"Port {taken} is taken by another program" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("claude", "warning"),
    [
        (FakeClaude(CliStatus.MISSING), "Install Claude Code to read posts."),
        (FakeClaude(CliStatus.TOO_OLD, version="2.1.200"), "Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer. Run: claude update"),
    ],
)
def test_start_up_warns_when_claude_code_is_missing_or_too_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: FakeClaude, warning: str) -> None:
    paths = copy_at(tmp_path)
    said: list[str] = []
    monkeypatch.setattr("where_to_go.claude_login.claude_cli", lambda: claude)

    Cli(paths, InstanceConfig.load(paths, environ={}), out=said.append)._warn_if_signed_out()

    assert said == [warning]
    assert claude.calls == 1
