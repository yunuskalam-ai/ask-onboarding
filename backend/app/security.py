"""Cross-site request protection (CSRF), in addition to the SameSite cookie.

The session cookie is SameSite=Lax, so browsers don't send it on cross-site
POSTs. But "site" means the registrable domain: on a shared host such as
*.sslip.io, someone else's subdomain can count as the same site. So every
state-changing request is also checked here: if the browser says where it
came from (the Origin header), that must be this server.

Requests without an Origin header are allowed: browsers always send it on
cross-origin POSTs, so its absence means a same-origin request from an older
browser, or a non-browser client (curl, the eval scripts) that has no
ambient cookies to abuse.
"""

from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def same_origin(origin: str, host: str) -> bool:
    """True if the Origin header names this server (scheme ignored: TLS ends at the proxy)."""
    if not origin or origin == "null":  # "null": sandboxed iframes, file:// pages
        return False
    netloc = urlsplit(origin).netloc.lower()
    return bool(netloc) and netloc == host.lower()


class OriginCheckMiddleware:
    """Refuse state-changing requests whose Origin is another site (403)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in STATE_CHANGING:
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            origin = headers.get("origin")
            if origin is not None and not same_origin(origin, headers.get("host", "")):
                response = JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
