from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

from where_to_go.launcher.paths import ProjectPaths

# A port few programs pick, so the app rarely has to move off it.
DEFAULT_PORT = 48765
DEFAULT_INSTANCE = "prod"
WORKTREE_INSTANCE = "dev"
APP_DATA_NAME = "where-to-go"


class ConfigError(ValueError):
    pass


class DotEnv:
    """The optional `.env` of a copy: `NAME=value` lines; `#` starts a comment."""

    @staticmethod
    def read(path: Path) -> dict[str, str]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        values = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            values[name.strip().removeprefix("export ").strip()] = DotEnv._unquoted(value.strip())
        return values

    @staticmethod
    def _unquoted(value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value.split(" #", 1)[0].strip()


@dataclass(frozen=True)
class InstanceConfig:
    """How this copy runs when nothing else is said.

    Everyone gets the same defaults: port 48765, the data in the
    user's data folder of the platform, the "prod" instance. `.env` in the copy overrides them, and
    `WHERE_TO_GO_*` variables override `.env`. A port set there is fixed; otherwise the copy keeps to the
    port it moved to when another program held its own (`paths.chosen_port`).
    A linked git worktree keeps its data in its own `data` folder, so work in progress never opens the
    real data by accident."""

    port: int
    data_dir: Path
    instance: str
    menu_bar_icon: bool
    port_fixed: bool = True

    ENV_PORT = "WHERE_TO_GO_PORT"
    ENV_DATA_DIR = "WHERE_TO_GO_DATA_DIR"
    ENV_INSTANCE = "WHERE_TO_GO_INSTANCE"

    @classmethod
    def load(cls, paths: ProjectPaths, environ: Mapping[str, str] = os.environ) -> InstanceConfig:
        dotenv = DotEnv.read(paths.env_file)
        set_port = environ.get(cls.ENV_PORT) or dotenv.get("PORT")
        port_text = set_port or cls._remembered_port(paths) or str(DEFAULT_PORT)
        data_text = environ.get(cls.ENV_DATA_DIR) or dotenv.get("DATA_DIR") or ""
        instance = environ.get(cls.ENV_INSTANCE) or dotenv.get("INSTANCE_ENV_NAME") or cls._default_instance(paths)
        return cls(
            port=cls._port(port_text),
            data_dir=cls._data_dir(paths, data_text),
            instance=instance,
            menu_bar_icon=dotenv.get("MENU_BAR_ICON", "0").strip() == "1",
            port_fixed=bool(set_port),
        )

    @staticmethod
    def _remembered_port(paths: ProjectPaths) -> str | None:
        try:
            text = paths.chosen_port.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text if text.isdigit() and 1 <= int(text) <= 65535 else None

    @staticmethod
    def default_data_dir() -> Path:
        return Path(user_data_dir(APP_DATA_NAME, appauthor=False))

    @staticmethod
    def _default_instance(paths: ProjectPaths) -> str:
        return WORKTREE_INSTANCE if paths.is_linked_worktree else DEFAULT_INSTANCE

    @classmethod
    def _data_dir(cls, paths: ProjectPaths, text: str) -> Path:
        if not text:
            return paths.root / "data" if paths.is_linked_worktree else cls.default_data_dir()
        path = Path(text).expanduser()
        return (path if path.is_absolute() else paths.writable / path).resolve()

    @staticmethod
    def _port(text: str) -> int:
        try:
            port = int(text)
        except ValueError:
            raise ConfigError(f"PORT must be a number, got {text!r}") from None
        if not 1 <= port <= 65535:
            raise ConfigError(f"PORT must be between 1 and 65535, got {port}")
        return port
