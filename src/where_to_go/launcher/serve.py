from __future__ import annotations

import logging

import uvicorn

from where_to_go.about import VERSION
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.records import ServerRecords
from where_to_go.launcher.spec import HOST, ServerSpec
from where_to_go.phone_page.secrets import platform_secret
from where_to_go.serving import AppWithInterface


def serve(paths: ProjectPaths, spec: ServerSpec) -> None:
    """Runs the server in this process until it is stopped. While it runs, its record in the copy's `.pids`
    tells `status`, `down` and the updater where it is and how to start it again."""
    logging.basicConfig(level=logging.INFO)
    app = create_app(lambda: Container.build(spec.data_dir, phone_token=platform_secret(spec.data_dir)))
    if spec.ui:
        app = AppWithInterface.build(app, spec.ui)
    records = ServerRecords(paths)
    record = records.register(spec, VERSION)
    try:
        uvicorn.run(app, host=HOST, port=spec.port)
    finally:
        records.unregister(record)
