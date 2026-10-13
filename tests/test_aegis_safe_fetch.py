"""SSRF protections in ``aegis.common.safe_fetch``."""

from __future__ import annotations

import contextlib
import gzip
import threading
import time
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from aegis.common.config import Settings
from aegis.common.safe_fetch import (
    BlockedDestinationError,
    FetchError,
    FetchTooLargeError,
    SafeFetcher,
    TooManyRedirectsError,
)

BLOCKED_URLS = [
    "http://0.0.0.0/",
    "http://10.0.0.1/",
    "http://100.64.0.1/",
    "http://127.0.0.1/",
    "http://169.254.10.10/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://224.0.0.1/",
    "http://240.0.0.1/",
    "http://[::]/",
    "http://[::1]/",
    "http://[fc00::1]/",
    "http://[fe80::1]/",
]

NUMERIC_HOST_URLS = [
    "http://2130706433/",
    "http://0x7f.1/",
    "http://017700000001/",
    "http://127.1/",
    "http://0x7f000001/",
]


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/ok":
            self._respond(200, b"hello", "text/plain")
        elif parsed.path == "/accept":
            self._respond(200, self.headers.get("accept", "").encode(), "text/plain")
        elif parsed.path == "/ua":
            self._respond(200, self.headers.get("user-agent", "").encode(), "text/plain")
        elif parsed.path == "/request-line":
            self._respond(200, self.requestline.encode(), "text/plain")
        elif parsed.path == "/redirect":
            self._respond(302, b"", "text/plain", location=query["to"][0])
        elif parsed.path == "/chain":
            remaining = int(query["n"][0])
            if remaining:
                self._respond(302, b"", "text/plain", location=f"/chain?n={remaining - 1}")
            else:
                self._respond(200, b"end", "text/plain")
        elif parsed.path == "/oversize":
            self._respond(200, b"x" * int(query["size"][0]), "application/octet-stream")
        elif parsed.path == "/gzip":
            self._respond(200, gzip.compress(b"0" * int(query["size"][0])), "text/plain", encoding="gzip")
        elif parsed.path == "/slow":
            self.send_response(200)
            self.send_header("content-type", "text/plain")
            self.send_header("content-length", "4")
            self.end_headers()
            time.sleep(float(query["seconds"][0]))
            self._write(b"slow")
        else:
            self._respond(404, b"missing", "text/plain")

    def _respond(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        location: str | None = None,
        encoding: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        if location is not None:
            self.send_header("location", location)
        if encoding is not None:
            self.send_header("content-encoding", encoding)
        self.end_headers()
        self._write(body)

    def _write(self, body: bytes) -> None:
        with contextlib.suppress(OSError):
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _test_settings(server: str, **overrides: object) -> Settings:
    values: dict[str, object] = {"fetch_allowed_ports": f"80,443,{urlsplit(server).port}"}
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def server() -> Iterator[str]:
    httpd = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def fetcher(server: str) -> SafeFetcher:
    return SafeFetcher(_test_settings(server), allow_cidrs_for_tests=["127.0.0.1/32"])


@pytest.mark.parametrize("url", BLOCKED_URLS)
async def test_blocks_private_and_reserved_literals(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch(url)


@pytest.mark.parametrize("url", NUMERIC_HOST_URLS)
async def test_blocks_numeric_host_forms(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch(url)


async def test_blocks_ipv4_mapped_loopback() -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch("http://[::ffff:127.0.0.1]/")


@pytest.mark.parametrize("url", ["http://169.254.169.254/", "http://[fd00:ec2::254]/"])
async def test_blocks_metadata_addresses(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch(url)


async def test_blocks_localhost() -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch("http://localhost/")


async def test_blocks_name_resolving_to_loopback() -> None:
    async def resolver(host: str, port: int) -> Sequence[str]:
        return ["127.0.0.1", "::1"]

    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings(), resolver=resolver).fetch("http://internal.test/")


async def test_blocks_name_that_rebinds_before_connect() -> None:
    calls: list[str] = []

    async def resolver(host: str, port: int) -> Sequence[str]:
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["127.0.0.1"]

    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings(), resolver=resolver).fetch("http://rebind.test/")
    assert len(calls) >= 2


@pytest.mark.parametrize("target", ["http://10.1.2.3/", "http://169.254.169.254/"])
async def test_blocks_redirect_to_private_address(fetcher: SafeFetcher, server: str, target: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await fetcher.fetch(f"{server}/redirect?to={quote(target, safe='')}")


@pytest.mark.parametrize("target", ["file:///etc/passwd", "gopher://127.0.0.1:70/1"])
async def test_blocks_redirect_to_disallowed_scheme(fetcher: SafeFetcher, server: str, target: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await fetcher.fetch(f"{server}/redirect?to={quote(target, safe='')}")


async def test_blocks_more_than_five_redirects(fetcher: SafeFetcher, server: str) -> None:
    with pytest.raises(TooManyRedirectsError):
        await fetcher.fetch(f"{server}/chain?n=6")


async def test_follows_up_to_five_redirects(fetcher: SafeFetcher, server: str) -> None:
    result = await fetcher.fetch(f"{server}/chain?n=5")
    assert result.status == 200
    assert result.body == b"end"
    assert result.redirects == 5


async def test_blocks_oversize_body(fetcher: SafeFetcher, server: str) -> None:
    with pytest.raises(FetchTooLargeError):
        await fetcher.fetch(f"{server}/oversize?size=4096", max_bytes=1024)


async def test_blocks_gzip_bomb(fetcher: SafeFetcher, server: str) -> None:
    with pytest.raises(FetchTooLargeError):
        await fetcher.fetch(f"{server}/gzip?size=1048576", max_bytes=1024)


async def test_decodes_gzip_body_within_the_cap(fetcher: SafeFetcher, server: str) -> None:
    result = await fetcher.fetch(f"{server}/gzip?size=64", max_bytes=1024)
    assert result.body == b"0" * 64


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@127.0.0.1/",
        "http://user@127.0.0.1/",
    ],
)
async def test_blocks_userinfo_urls(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/", "https://example.test:8443/"])
async def test_blocks_disallowed_ports(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch(url)


async def test_blocks_extra_blocked_cidrs_from_settings() -> None:
    fetcher = SafeFetcher(Settings(fetch_extra_blocked_cidrs="203.0.113.0/24"))
    with pytest.raises(BlockedDestinationError):
        await fetcher.fetch("http://203.0.113.10/")


async def test_fetch_returns_body_and_metadata(fetcher: SafeFetcher, server: str) -> None:
    result = await fetcher.fetch(f"{server}/ok")
    assert result.status == 200
    assert result.body == b"hello"
    assert result.content_type == "text/plain"
    assert result.headers["content-type"] == "text/plain"
    assert result.final_url == f"{server}/ok"
    assert result.redirects == 0
    assert result.peer_ip == "127.0.0.1"


async def test_fetch_sends_configured_headers(server: str) -> None:
    fetcher = SafeFetcher(
        _test_settings(server, fetch_user_agent="aegis-fetch/test"),
        allow_cidrs_for_tests=["127.0.0.1/32"],
    )
    accept = await fetcher.fetch(f"{server}/accept", accept="application/json")
    assert accept.body == b"application/json"
    user_agent = await fetcher.fetch(f"{server}/ua")
    assert user_agent.body == b"aegis-fetch/test"


async def test_local_server_is_blocked_without_test_allow_list(server: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(_test_settings(server)).fetch(f"{server}/ok")


async def test_fetch_times_out(server: str) -> None:
    fetcher = SafeFetcher(
        _test_settings(server, fetch_timeout_seconds=0.3),
        allow_cidrs_for_tests=["127.0.0.1/32"],
    )
    with pytest.raises(FetchError):
        await fetcher.fetch(f"{server}/slow?seconds=2")


async def test_proxy_destination_checks_run_first() -> None:
    with pytest.raises(BlockedDestinationError):
        await SafeFetcher(Settings()).fetch("http://169.254.169.254/", proxy="http://127.0.0.1:3128")


async def test_fetch_through_http_proxy(server: str) -> None:
    async def resolver(host: str, port: int) -> Sequence[str]:
        return ["93.184.216.34"]

    fetcher = SafeFetcher(
        _test_settings(server),
        resolver=resolver,
        allow_cidrs_for_tests=["127.0.0.1/32"],
    )
    result = await fetcher.fetch("http://target.test/request-line", proxy=server)
    assert result.status == 200
    assert result.body == b"GET http://target.test/request-line HTTP/1.1"
    assert result.peer_ip == "127.0.0.1"


async def test_proxy_scheme_is_validated() -> None:
    with pytest.raises(FetchError):
        await SafeFetcher(Settings()).fetch("http://192.0.2.10/", proxy="socks5://127.0.0.1:1080")


def test_fetch_settings_have_safe_defaults() -> None:
    settings = Settings()
    assert settings.fetch_max_bytes == 10 * 1024 * 1024
    assert settings.fetch_timeout_seconds == 15.0
    assert settings.fetch_user_agent.startswith("aegis-fetch/")
    assert settings.fetch_allowed_ports == "80,443"
    assert settings.fetch_extra_blocked_cidrs == ""
