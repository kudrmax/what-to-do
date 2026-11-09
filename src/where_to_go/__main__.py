from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from where_to_go.api import create_app, default_data_dir
from where_to_go.container import Container

DEFAULT_PORT = 18765


def main() -> None:
    parser = argparse.ArgumentParser(prog="where-to-go", description="Local backend of «Чем заняться»")
    parser.add_argument("--data", type=Path, default=default_data_dir(), help="folder for the database and images")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app = create_app(lambda: Container.build(args.data))
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
