from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

HOST = "127.0.0.1"
NO_UI = "--no-ui"


@dataclass(frozen=True)
class ServerSpec:
    """How a server runs: what `up` starts and what an update restarts the same way.
    `ui` is the built interface it serves at the root; without one it serves the API alone."""

    port: int
    data_dir: Path
    ui: Path | None
    instance: str

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    @property
    def version_url(self) -> str:
        return f"{self.url}/api/version" if self.ui else f"{self.url}/version"

    def arguments(self) -> list[str]:
        """The command-line options that start a server like this one, for `up` and `serve`."""
        ui = ["--ui", str(self.ui)] if self.ui else [NO_UI]
        return ["--port", str(self.port), "--data", str(self.data_dir), "--instance", self.instance, *ui]

    def to_json(self) -> dict[str, object]:
        return {**asdict(self), "data_dir": str(self.data_dir), "ui": str(self.ui) if self.ui else None}

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ServerSpec:
        ui = data.get("ui")
        return cls(
            port=int(str(data["port"])),
            data_dir=Path(str(data["data_dir"])),
            ui=Path(str(ui)) if ui else None,
            instance=str(data.get("instance") or ""),
        )


@dataclass(frozen=True)
class ServerRecord:
    """What a running server writes about itself: the process, so a reused pid is not taken for it,
    and how it was started."""

    pid: int
    create_time: float
    spec: ServerSpec
    version: str

    def dumps(self) -> str:
        return json.dumps({"pid": self.pid, "create_time": self.create_time, "version": self.version, **self.spec.to_json()}, indent=2)

    @classmethod
    def loads(cls, text: str) -> ServerRecord:
        data = json.loads(text)
        return cls(pid=int(data["pid"]), create_time=float(data["create_time"]), spec=ServerSpec.from_json(data), version=str(data.get("version", "")))


class LegacyCommandLine:
    """Reads how a server was started from its command line, for servers that wrote no record:
    those of releases before 1.16 and those started by hand."""

    MARKERS = ("where-to-go", "where_to_go")

    @classmethod
    def is_server(cls, cmdline: list[str]) -> bool:
        tail = cls.app_arguments(cmdline)
        if tail is None:
            return False
        return not tail or tail[0] == "serve" or tail[0].startswith("-")

    @classmethod
    def spec(cls, cmdline: list[str], cwd: Path, port: int, default_data: Path, instance: str) -> ServerSpec:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--port", type=int, default=port)
        parser.add_argument("--data", type=Path, default=default_data)
        parser.add_argument("--ui", type=Path)
        parser.add_argument("--instance", default=instance)
        arguments = [argument for argument in cls.app_arguments(cmdline) or [] if argument != "serve"]
        known, _ = parser.parse_known_args(arguments)
        ui = known.ui if known.ui is None or known.ui.is_absolute() else cwd / known.ui
        data = known.data if known.data.is_absolute() else cwd / known.data
        return ServerSpec(port=known.port, data_dir=data, ui=ui, instance=known.instance)

    @classmethod
    def app_arguments(cls, cmdline: list[str]) -> list[str] | None:
        """What follows the app's command in a command line; None when it does not run the app."""
        for index, part in enumerate(cmdline):
            name = Path(part).name
            if name.removesuffix(".exe") in cls.MARKERS:
                return cmdline[index + 1:]
            if part == "-m" and index + 1 < len(cmdline) and cmdline[index + 1] in cls.MARKERS:
                return cmdline[index + 2:]
        return None
