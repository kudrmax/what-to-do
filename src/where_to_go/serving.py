from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope


class HashedAssets(StaticFiles):
    """Build files whose names carry a hash of their content: a new build gets new names, so a copy never goes stale."""

    CACHE_CONTROL = "public, max-age=31536000, immutable"

    def file_response(self, full_path: os.PathLike[str] | str, stat_result: os.stat_result, scope: Scope, status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = self.CACHE_CONTROL
        return response


class AppWithInterface:
    """Serves a built web interface at the root and the API under /api, from one address.

    The API knows nothing about the interface: it is mounted as it is, and any interface build folder will do.
    Paths the interface routes itself (/calendar, /event/12) get its index.html.
    The page is checked with the server on every load: without that WebKit keeps showing an old index.html
    after an update, and that page loads the old build from its cache.
    """

    API_PREFIX = "/api"
    PAGE_CACHE_CONTROL = "no-cache"

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
        app.mount("/assets", HashedAssets(directory=interface / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def interface_page(path: str) -> FileResponse:
            file = (interface / path).resolve()
            served = file if path and file.is_file() and file.is_relative_to(interface.resolve()) else index
            return FileResponse(served, headers={"Cache-Control": cls.PAGE_CACHE_CONTROL})

        return app
