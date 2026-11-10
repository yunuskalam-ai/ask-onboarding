"""Who is on the other end of a request: their IP address and browser string.

A small ASGI middleware stores them for the current request, so the audit log
(auth.record) can add them without every endpoint passing the request along.

The IP: requests arrive through nginx (and Caddy when deployed), so the
direct peer is a proxy. nginx works out the real client address (its realip
settings in frontend/nginx.conf) and sends it as X-Real-IP. That header is
believed **only from a private or loopback peer**, which in production can only
be nginx: the API has no public port. From anyone else it is ignored, so a
client can't put a made-up address in the audit log.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from ipaddress import ip_address

from starlette.types import ASGIApp, Receive, Scope, Send

MAX_USER_AGENT = 400  # long enough for any real browser; caps what a client can make us store


@dataclass(frozen=True)
class ClientInfo:
    ip: str | None
    user_agent: str | None


_current: ContextVar[ClientInfo | None] = ContextVar("client_info", default=None)
_UNKNOWN = ClientInfo(None, None)  # outside a request: background jobs, scripts


def current() -> ClientInfo:
    """The client of the request being handled."""
    return _current.get() or _UNKNOWN


def _valid_ip(value: str | None) -> str | None:
    try:
        return str(ip_address(value.strip())) if value else None
    except ValueError:
        return None


def client_ip(peer: str | None, real_ip_header: str | None) -> str | None:
    """The client's address: X-Real-IP if the peer is our own proxy, else the peer itself."""
    peer_ip = _valid_ip(peer)
    if peer_ip is None:
        return None
    address = ip_address(peer_ip)
    if (address.is_private or address.is_loopback) and (forwarded := _valid_ip(real_ip_header)):
        return forwarded
    return peer_ip


class ClientInfoMiddleware:
    """Record the client's IP and browser for the length of each HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        peer = scope["client"][0] if scope.get("client") else None
        agent = headers.get("user-agent", "")[:MAX_USER_AGENT] or None
        token = _current.set(ClientInfo(client_ip(peer, headers.get("x-real-ip")), agent))
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
