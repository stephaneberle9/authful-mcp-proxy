from contextlib import asynccontextmanager

import pytest

from authsome_mcp_proxy.host_router import HostRouter, _request_host, host_of

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeApp:
    """Minimal stand-in for a StarletteWithLifespan child app.

    Records the scopes it is called with and whether its lifespan is currently
    entered, which is what the routing and lifespan tests assert on.
    """

    def __init__(self, name):
        self.name = name
        self.calls = []
        self.events = []
        self.started = False

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)

    def lifespan(self, app):
        assert app is self, "child lifespan must be passed its own app"

        @asynccontextmanager
        async def _cm():
            self.started = True
            self.events.append("startup")
            try:
                yield
            finally:
                self.started = False
                self.events.append("shutdown")

        return _cm()


async def noop_receive():
    """Routing tests dispatch but never read a body; FakeApp ignores these.

    Real callables rather than None so the calls match HostRouter's ASGI
    signature -- a None here would type-check as a lie about the contract.
    """
    raise AssertionError("routing tests never read the request body")


async def noop_send(message):
    raise AssertionError("routing tests never send a response")


def http_scope(host=None):
    headers = [(b"accept", b"*/*")]
    if host is not None:
        headers.insert(0, (b"host", host.encode("latin-1")))
    return {"type": "http", "headers": headers}


# ---------------------------------------------------------------------------
# host_of
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_url,expected",
    [
        ("https://mcp.example.com", "mcp.example.com"),
        ("https://MCP.Example.COM/", "mcp.example.com"),
        ("https://mcp.example.com:8443/base", "mcp.example.com"),
        ("http://localhost:8000", "localhost"),
        ("https://[::1]:8000", "::1"),
    ],
)
def test_host_of_normalizes(base_url, expected):
    """Case, port and path are stripped so table keys and Host headers compare
    on the same footing."""
    assert host_of(base_url) == expected


@pytest.mark.parametrize("bad", ["mcp.example.com", "", "/just/a/path"])
def test_host_of_rejects_values_without_a_hostname(bad):
    """A bare hostname is a common config slip; catching it here beats shipping
    an identity that can never be routed to."""
    with pytest.raises(ValueError, match="no hostname"):
        host_of(bad)


# ---------------------------------------------------------------------------
# _request_host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [
        ("mcp.example.com", "mcp.example.com"),
        ("MCP.Example.com", "mcp.example.com"),
        ("mcp.example.com:8443", "mcp.example.com"),
        ("  mcp.example.com  ", "mcp.example.com"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
    ],
)
def test_request_host_parses_header(header, expected):
    assert _request_host(http_scope(header)) == expected


@pytest.mark.parametrize("header", [None, ""])
def test_request_host_returns_none_without_a_usable_header(header):
    """HTTP/1.0 clients and some probes send no Host at all."""
    assert _request_host(http_scope(header)) is None


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_rejects_empty_app_map():
    with pytest.raises(ValueError, match="at least one app"):
        HostRouter({}, canonical_base_url="https://mcp.example.com")


def test_rejects_base_urls_sharing_a_hostname():
    """Two identities on one hostname cannot be told apart by the Host header,
    so the last one would silently shadow the first."""
    apps = {
        "https://mcp.example.com": FakeApp("a"),
        "https://mcp.example.com:8443": FakeApp("b"),
    }
    with pytest.raises(ValueError, match="same hostname"):
        HostRouter(apps, canonical_base_url="https://mcp.example.com")


def test_rejects_canonical_not_among_apps():
    apps = {"https://mcp.example.com": FakeApp("a")}
    with pytest.raises(ValueError, match="not among the routed base URLs"):
        HostRouter(apps, canonical_base_url="https://other.example.com")


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_each_host_to_its_own_app():
    """The whole point: a request for the alias hostname is served by the alias
    identity, not by the canonical one."""
    primary, alias = FakeApp("primary"), FakeApp("alias")
    router = HostRouter(
        {"https://mcp.example.io": primary, "https://mcp.example.com": alias},
        canonical_base_url="https://mcp.example.io",
    )

    await router(http_scope("mcp.example.com"), noop_receive, noop_send)
    assert len(alias.calls) == 1
    assert primary.calls == []

    await router(http_scope("mcp.example.io"), noop_receive, noop_send)
    assert len(primary.calls) == 1


@pytest.mark.asyncio
async def test_matches_host_case_insensitively_and_ignores_port():
    primary, alias = FakeApp("primary"), FakeApp("alias")
    router = HostRouter(
        {"https://mcp.example.io": primary, "https://mcp.example.com": alias},
        canonical_base_url="https://mcp.example.io",
    )

    await router(http_scope("MCP.Example.COM:443"), noop_receive, noop_send)
    assert len(alias.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("host", [None, "10.0.1.7", "unknown.example.net"])
async def test_falls_back_to_canonical_for_absent_or_unknown_host(host):
    """Kubernetes probes address the pod IP and scanners send anything at all;
    both must still get a working app rather than a routing error."""
    primary, alias = FakeApp("primary"), FakeApp("alias")
    router = HostRouter(
        {"https://mcp.example.io": primary, "https://mcp.example.com": alias},
        canonical_base_url="https://mcp.example.io",
    )

    await router(http_scope(host), noop_receive, noop_send)
    assert len(primary.calls) == 1
    assert alias.calls == []


@pytest.mark.asyncio
async def test_single_host_router_serves_everything_from_its_only_app():
    """The single-hostname deployment runs the same code path, so it must stay
    indistinguishable from having no router at all."""
    only = FakeApp("only")
    router = HostRouter(
        {"https://mcp.example.com": only},
        canonical_base_url="https://mcp.example.com",
    )

    await router(http_scope("mcp.example.com"), noop_receive, noop_send)
    await router(http_scope("something.else"), noop_receive, noop_send)
    await router(http_scope(None), noop_receive, noop_send)
    assert len(only.calls) == 3


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


class LifespanDriver:
    """Drives the ASGI lifespan protocol against a router and records replies."""

    def __init__(self):
        self.incoming = ["lifespan.startup", "lifespan.shutdown"]
        self.sent = []

    async def receive(self):
        return {"type": self.incoming.pop(0)}

    async def send(self, message):
        self.sent.append(message)


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_every_child():
    """Starlette only propagates lifespan into apps reached through routing, so
    children entered by the router would otherwise never start their session
    managers."""
    primary, alias = FakeApp("primary"), FakeApp("alias")
    router = HostRouter(
        {"https://mcp.example.io": primary, "https://mcp.example.com": alias},
        canonical_base_url="https://mcp.example.io",
    )
    driver = LifespanDriver()

    await router({"type": "lifespan"}, driver.receive, driver.send)

    assert [m["type"] for m in driver.sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]
    assert primary.events == ["startup", "shutdown"]
    assert alias.events == ["startup", "shutdown"]
    assert not primary.started and not alias.started


@pytest.mark.asyncio
async def test_failing_child_startup_reports_failure_and_unwinds():
    """A half-started server must not report itself ready: the already-started
    children are torn down and uvicorn is told startup failed."""

    class ExplodingApp(FakeApp):
        def lifespan(self, app):
            @asynccontextmanager
            async def _cm():
                raise RuntimeError("session manager unavailable")
                yield  # pragma: no cover - unreachable, satisfies the CM shape

            return _cm()

    healthy = FakeApp("healthy")
    router = HostRouter(
        {
            "https://mcp.example.io": healthy,
            "https://mcp.example.com": ExplodingApp("x"),
        },
        canonical_base_url="https://mcp.example.io",
    )
    driver = LifespanDriver()

    with pytest.raises(RuntimeError, match="session manager unavailable"):
        await router({"type": "lifespan"}, driver.receive, driver.send)

    assert driver.sent[-1]["type"] == "lifespan.startup.failed"
    assert healthy.events == ["startup", "shutdown"]
