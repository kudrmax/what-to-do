from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from where_to_go.api import create_app, default_data_dir
from where_to_go.container import Container
from where_to_go.serving import AppWithInterface

DEFAULT_PORT = 18765


def main() -> None:
    parser = argparse.ArgumentParser(prog="where-to-go", description="Local backend of «Чем заняться»")
    parser.add_argument("--data", type=Path, default=default_data_dir(), help="folder for the database and images")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ui", type=Path, help="a built web interface to serve at the root; the API moves to /api")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app = create_app(lambda: Container.build(args.data))
    if args.ui:
        app = AppWithInterface.build(app, args.ui)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
