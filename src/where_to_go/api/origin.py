from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class SameOriginOnly:
    """Refuses requests a browser sends from another site, so a page open in the browser cannot use the app.

    A browser names the page's site in `Origin`; the app's own pages are served from the address the request
    goes to. Requests without `Origin` come from programs, not from web pages, and pass.
    """

    MESSAGE = "Requests from other sites are not allowed"

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._allowed(scope):
            await JSONResponse({"detail": self.MESSAGE}, status_code=403)(scope, receive, send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    def _allowed(scope: Scope) -> bool:
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is None:
            return True
        own = f"{scope['scheme']}://{headers.get('host', '')}"
        return origin.lower() == own.lower()
