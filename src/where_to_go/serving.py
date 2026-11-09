from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


class AppWithInterface:
    """Serves a built web interface at the root and the API under /api, from one address.

    The API knows nothing about the interface: it is mounted as it is, and any interface build folder will do.
    Paths the interface routes itself (/calendar, /event/12) get its index.html.
    """

    API_PREFIX = "/api"

    @classmethod
    def build(cls, api: FastAPI, interface: Path) -> FastAPI:
        index = interface / "index.html"
        if not index.is_file():
            raise FileNotFoundError(f"no index.html in {interface}: build the interface first")
        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            async with api.router.lifespan_context(api):
                yield

        app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
        app.mount(cls.API_PREFIX, api)
        app.mount("/assets", StaticFiles(directory=interface / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def interface_page(path: str) -> FileResponse:
            file = (interface / path).resolve()
            if path and file.is_file() and file.is_relative_to(interface.resolve()):
                return FileResponse(file)
            return FileResponse(index)

        return app
