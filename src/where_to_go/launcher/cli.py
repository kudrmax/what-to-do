from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from where_to_go.launcher.config import ConfigError, InstanceConfig
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.spec import ServerSpec
from where_to_go.launcher.updater import DETACHED_CHILD, UpdateFailedError, UpdateLog, Updater

if TYPE_CHECKING:
    from where_to_go.launcher.control import ServerControl

APP_NAME = "What To Do"
PROG = "where-to-go"
COMMANDS = ("serve", "up", "down", "restart", "status", "port", "logs", "build", "update", "uninstall")
NOT_RUNNING_EXIT = 3
BANNER_PROD = "\033[1;32m"
BANNER_OTHER = "\033[1;33m"
RESET = "\033[0m"
RULE = "━" * 40


class Cli:
    """`where-to-go <command>`: the one way to run, stop, update and remove a copy, the same on every platform."""

    def __init__(self, paths: ProjectPaths, config: InstanceConfig, out: Callable[[str], None] | None = None) -> None:
        self._paths = paths
        self._config = config
        self._out = out or say

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=PROG,
            description=f"Run «{APP_NAME}» on this computer. Without a command, runs the server in this terminal until Ctrl+C.",
            epilog="Commands: " + ", ".join(COMMANDS) + f". `{PROG} <command> --help` tells more.",
        )
        commands = parser.add_subparsers(dest="command", metavar="<command>")

        serve = commands.add_parser("serve", help="run the server in this terminal until Ctrl+C (the default)")
        self._server_options(serve, ui_default=None)
        serve.set_defaults(handler=self.serve)

        up = commands.add_parser("up", help="build the interface if needed and start the app in the background")
        self._server_options(up, ui_default=self._paths.dist)
        up.add_argument("--no-build", action="store_true", help="use the interface as it is built")
        up.add_argument("--open", action="store_true", help="open the app in the browser once it runs")
        up.set_defaults(handler=self.up)

        down = commands.add_parser("down", help="stop the app and everything it started")
        down.add_argument("--port", type=int, help="stop only the server on this port")
        down.set_defaults(handler=self.down)

        restart = commands.add_parser("restart", help="stop the app and start it again as it ran")
        restart.set_defaults(handler=self.restart)

        status = commands.add_parser("status", help="whether the app runs, where and with which data")
        status.add_argument("--json", action="store_true", help="answer in JSON")
        status.set_defaults(handler=self.status)

        port = commands.add_parser("port", help="the port the app starts on; moves to a free one when another program holds it")
        port.set_defaults(handler=self.port)

        logs = commands.add_parser("logs", help="the logs of the app and of its updates")
        logs.add_argument("--lines", type=int, default=50, help="how many last lines to show first (default 50)")
        logs.add_argument("--no-follow", action="store_true", help="show the last lines and quit")
        logs.set_defaults(handler=self.logs)

        build = commands.add_parser("build", help="build the interface if its sources changed")
        build.set_defaults(handler=self.build)

        update = commands.add_parser("update", help="update this copy to the latest release and restart it")
        update.add_argument("--background", action="store_true", help="run the update on its own and return at once")
        update.add_argument(DETACHED_CHILD, action="store_true", help=argparse.SUPPRESS)
        update.set_defaults(handler=self.update)

        uninstall = commands.add_parser("uninstall", help="stop the app and remove it from this computer")
        uninstall.add_argument("--yes", action="store_true", help="ask nothing: remove the app and the data")
        uninstall.add_argument("--keep-data", action="store_true", help="keep the data folder")
        uninstall.add_argument("--data", type=Path, default=self._config.data_dir, help=f"the data folder (default: {self._config.data_dir})")
        uninstall.set_defaults(handler=self.uninstall)
        return parser

    def run(self, argv: list[str]) -> int:
        if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
            argv = ["serve", *argv]
        arguments = self.parser().parse_args(argv)
        try:
            return int(arguments.handler(arguments))
        except KeyboardInterrupt:
            return 130
        except (RuntimeError, OSError, ConfigError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

    def serve(self, arguments: argparse.Namespace) -> int:
        from where_to_go.launcher.serve import serve

        serve(self._paths, self._spec(arguments))
        return 0

    def port(self, _: argparse.Namespace) -> int:
        """Prints only the number on standard output, for the macOS app; notes go to standard error."""
        from where_to_go.launcher.control import ServerControl

        control = ServerControl(self._paths, self._config, say=lambda text: print(text, file=sys.stderr, flush=True))
        self._out(str(control.choose_port()))
        return 0

    def up(self, arguments: argparse.Namespace) -> int:
        if arguments.port is None:
            arguments.port = self._control().choose_port()
        spec = self._spec(arguments)
        self._control().up(spec, build=not arguments.no_build)
        self._banner(spec)
        self._warn_if_reader_not_ready([spec.data_dir])
        if arguments.open:
            webbrowser.open(spec.url)
        return 0

    def down(self, arguments: argparse.Namespace) -> int:
        self._control().down(arguments.port)
        return 0

    def restart(self, _: argparse.Namespace) -> int:
        for spec in self._control().restart():
            self._banner(spec)
        return 0

    def status(self, arguments: argparse.Namespace) -> int:
        control = self._control()
        servers = control.running(None)
        if arguments.json:
            self._out(json.dumps(
                {
                    "running": bool(servers),
                    "servers": [{**server.spec.to_json(), "pid": server.process.pid, "url": server.spec.url, "version": control.version_of(server.spec) or server.version} for server in servers],
                    "config": {"port": self._config.port, "data_dir": str(self._config.data_dir), "instance": self._config.instance},
                },
                indent=2,
            ))
            return 0 if servers else NOT_RUNNING_EXIT
        if not servers:
            self._out(f"{APP_NAME} is not running.")
            self._rows([("Starts on", f"http://127.0.0.1:{self._config.port}"), ("Data", str(self._config.data_dir)), ("Start it", f"{PROG} up")])
            return NOT_RUNNING_EXIT
        for server in servers:
            self._out(f"{APP_NAME} is running.")
            self._rows([
                ("Address", server.spec.url),
                ("PID", str(server.process.pid)),
                ("Version", control.version_of(server.spec) or server.version or "unknown"),
                ("Data", str(server.spec.data_dir)),
                ("Instance", server.spec.instance),
                ("Log", str(self._paths.app_log)),
            ])
        self._warn_if_reader_not_ready([server.spec.data_dir for server in servers])
        return 0

    def logs(self, arguments: argparse.Namespace) -> int:
        from where_to_go.launcher.logs import LogFollower

        follower = LogFollower([("app", self._paths.app_log), ("update", self._paths.update_log)], self._out)
        try:
            follower.run(arguments.lines, follow=not arguments.no_follow)
        except KeyboardInterrupt:
            pass
        return 0

    def build(self, _: argparse.Namespace) -> int:
        if not self._control().build():
            self._out("The interface is up to date.")
        return 0

    def update(self, arguments: argparse.Namespace) -> int:
        if arguments.background:
            try:
                pid = Updater.start_in_background(self._paths)
            except UpdateFailedError as error:
                print(f"ERROR: {error}", file=sys.stderr)
                return 1
            self._out(f"Updating in the background (PID {pid}). Follow it with: {PROG} logs")
            return 0
        log = UpdateLog(self._paths.update_log, echo=None if arguments.detached_child else sys.stdout)
        if self._paths.bundle is not None:
            from where_to_go.launcher.bundle_updater import BundleUpdater

            return BundleUpdater(self._paths, self._config, log, self._paths.bundle).run()
        return Updater(self._paths, self._config, log).run()

    def uninstall(self, arguments: argparse.Namespace) -> int:
        from where_to_go.launcher.uninstall import Uninstaller

        if self._paths.bundle is not None:
            print(f"ERROR: to uninstall the app, quit it and drag {self._paths.bundle.app.name} from Applications to the Trash.", file=sys.stderr)
            return 2
        uninstaller = Uninstaller(self._paths, self._control(), arguments.data.resolve(), say=self._out)
        delete_data = not arguments.keep_data
        if not arguments.yes:
            if not sys.stdin.isatty():
                print("ERROR: run it in a terminal to answer its questions, or confirm everything with --yes.", file=sys.stderr)
                return 2
            self._out(f"This stops {APP_NAME} and removes it from this computer.")
            for app in uninstaller.apps():
                self._out(f"  The macOS app {app} goes to the {self._trash_name()}.")
            if not self._confirm("Uninstall?"):
                self._out("Nothing was changed.")
                return 1
            if delete_data and uninstaller.data_dir.exists():
                delete_data = self._confirm(f"Also delete your events, sources and settings in {uninstaller.data_dir}? They go to the {self._trash_name()}.")
        report = uninstaller.run(delete_data)
        for path in report.removed:
            self._out(f"Moved to the {self._trash_name()}: {path}")
        for path in report.kept:
            self._out(f"Kept your data: {path}")
        for path, reason in report.failed:
            self._out(f"Couldn't move {path} to the {self._trash_name()} ({reason}); delete it by hand.")
        self._out(f"\nLast step: delete the folder {self._paths.root}: it holds the app's code and the packages it installed.")
        return 1 if report.failed else 0

    def _spec(self, arguments: argparse.Namespace) -> ServerSpec:
        ui = None if arguments.no_ui else arguments.ui
        return ServerSpec(
            port=arguments.port if arguments.port is not None else self._config.port,
            data_dir=arguments.data.expanduser().resolve(),
            ui=ui.expanduser().resolve() if ui else None,
            instance=arguments.instance,
        )

    def _server_options(self, parser: argparse.ArgumentParser, ui_default: Path | None) -> None:
        config = self._config
        parser.add_argument("--port", type=int, default=None, help=f"the port of http://127.0.0.1:<port> (default: {config.port}, or a free one nearby when another program holds it)")
        parser.add_argument("--data", type=Path, default=config.data_dir, help=f"folder for the database and images (default: {config.data_dir})")
        parser.add_argument("--ui", type=Path, default=ui_default, help="a built web interface to serve at the root; the API moves to /api")
        parser.add_argument("--no-ui", action="store_true", help="serve the API alone")
        parser.add_argument("--instance", default=config.instance, help=f"the label of this copy (default: {config.instance})")

    def _control(self) -> ServerControl:
        from where_to_go.launcher.control import ServerControl

        return ServerControl(self._paths, self._config, say=self._out)

    def _banner(self, spec: ServerSpec) -> None:
        colour, reset = (BANNER_PROD if spec.instance == "prod" else BANNER_OTHER, RESET) if sys.stdout.isatty() else ("", "")
        self._out(f"\n{colour}{RULE}")
        self._out(f"  {APP_NAME}  [instance: {spec.instance}]")
        self._out(f"  Data: {spec.data_dir}")
        self._out(f"{RULE}{reset}")
        self._out(f"→ {spec.url}\n")

    def _warn_if_reader_not_ready(self, data_dirs: list[Path]) -> None:
        from where_to_go.active_provider import ActiveProvider
        from where_to_go.settings import LlmProvider

        for provider in dict.fromkeys(ActiveProvider.of(folder) for folder in data_dirs):
            if provider is LlmProvider.CODEX:
                self._warn_if_codex_not_ready()
            else:
                self._warn_if_claude_not_ready()

    def _warn_if_codex_not_ready(self) -> None:
        """Only installed and new enough: both are quick. The tool guard runs Codex for up to 20 seconds, and the app
        runs it before every call anyway; whether someone is signed in needs a running app-server. The app says both
        on the first refresh instead."""
        from where_to_go.codex_login import CODEX_INSTALL_COMMANDS, CodexHome, codex_cli, codex_unavailable_hint
        from where_to_go.installed_cli import CliStatus

        found = codex_cli(codex_home=CodexHome.default()).find()
        if found.status is not CliStatus.READY or found.path is None:
            update = f" Run: {found.update_command}" if found.update_command and found.status is CliStatus.TOO_OLD else ""
            self._out(f"{codex_unavailable_hint(found)}.{update}")
            if found.status is CliStatus.MISSING:
                first, *others = CODEX_INSTALL_COMMANDS
                self._out(f"Run: {first}")
                for other in others:
                    self._out(f"Or: {other}")

    def _warn_if_claude_not_ready(self) -> None:
        from where_to_go.claude_login import CLAUDE_INSTALL_COMMAND, SIGN_IN_HINT, ClaudeLogin, claude_cli, unavailable_hint
        from where_to_go.reader_sign_in import ReaderSignIn
        from where_to_go.installed_cli import CliStatus

        claude = claude_cli()
        found = claude.find()
        if found.status is not CliStatus.READY:
            update = f" Run: {found.update_command}" if found.update_command else ""
            self._out(f"{unavailable_hint(found)}.{update}")
            if found.status is CliStatus.MISSING:
                self._out(f"Run: {CLAUDE_INSTALL_COMMAND}")
        elif ClaudeLogin(claude).state_of(found) is ReaderSignIn.SIGNED_OUT:
            self._out(f"Claude Code is not signed in, so refreshes can't read posts. {SIGN_IN_HINT}.")

    def _rows(self, rows: list[tuple[str, str]]) -> None:
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            self._out(f"  {label.ljust(width)}  {value}")

    @staticmethod
    def _confirm(question: str) -> bool:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")

    @staticmethod
    def _trash_name() -> str:
        return "Recycle Bin" if sys.platform == "win32" else "Trash"


def say(text: str) -> None:
    print(text, flush=True)


def _speak_utf8() -> None:
    """Redirected output on Windows defaults to the console's code page, which cannot print the arrow."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> None:
    _speak_utf8()
    paths = ProjectPaths.here()
    try:
        config = InstanceConfig.load(paths)
    except ConfigError as error:
        print(f"ERROR in {paths.env_file}: {error}", file=sys.stderr)
        sys.exit(2)
    sys.exit(Cli(paths, config).run(sys.argv[1:] if argv is None else argv))
