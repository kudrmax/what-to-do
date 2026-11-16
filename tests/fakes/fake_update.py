"""`where-to-go update` with the updater's helpers replaced by fake_cli.py, for the Update button's tests:
`--background` starts it the way the app does, `update --detached-child` is the update itself."""

import os
import sys
from pathlib import Path

from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.macos_apps import MacApps
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.updater import DETACHED_CHILD, UpdateLog, Updater

FAKE_CLI = str(Path(__file__).with_name("fake_cli.py"))


def main() -> int:
    paths = ProjectPaths(Path.cwd())
    if DETACHED_CHILD in sys.argv:
        config = InstanceConfig(port=0, data_dir=paths.root / "data", instance="prod", menu_bar_icon=False)
        updater = Updater(
            paths,
            config,
            UpdateLog(paths.update_log, echo=None),
            cli=[sys.executable, FAKE_CLI],
            package_sync=[sys.executable, FAKE_CLI, "sync"],
            apps=MacApps(Path(os.environ["UPDATE_APPS_DIR"])),
            macos=True,
            app_builder=[sys.executable, FAKE_CLI, "app"],
        )
        return updater.run()
    Updater.start_in_background(paths, cli=[sys.executable, __file__])
    return 0


if __name__ == "__main__":
    sys.exit(main())
