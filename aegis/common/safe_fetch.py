"""SSRF-safe HTTP fetching for URLs supplied by analysts and remote platforms.

Every server-side fetch of an untrusted URL (manual submission, media download,
source-removed checks) goes through :class:`SafeFetcher`, which enforces:

* ``http`` and ``https`` only, no URL userinfo, and ports limited to
  ``fetch_allowed_ports`` (default ``80``/``443``). Numeric host forms such as
  ``2130706433``, ``0x7f.1``, and ``017700000001`` are parsed as IP addresses
  instead of being handed to the resolver.
* Every hostname is resolved and the fetch is rejected when *any* returned
  address is blocked: the private, loopback, link-local, shared, multicast,
  reserved, and metadata ranges fixed by D-08, plus ``::/128``, IPv4-mapped
  IPv6 (``::ffff:0:0/96``), NAT64 (``64:ff9b::/96``), IPv4-compatible IPv6,
  and the operator's ``fetch_extra_blocked_cidrs``.
* Pinning. ``httpx`` 0.28.1 exposes no hook for a custom network backend:
  ``httpx.AsyncHTTPTransport`` builds its own ``httpcore`` pool and accepts no
  ``network_backend``. The fetcher therefore wraps an ``httpcore`` 1.0.9
  ``AsyncConnectionPool`` in a small ``httpx.AsyncBaseTransport`` and installs
  an :class:`httpcore.AsyncNetworkBackend` whose ``connect_tcp`` resolves,
  filters, and connects to an allowed address. This was checked against the
  installed ``httpx``/``httpcore`` sources. TLS still uses the original
  hostname for SNI and certificate verification, because httpcore passes the
  request origin as ``server_hostname`` while the socket goes to the vetted
  address. The lookup inside ``connect_tcp`` is the authoritative one: a name
  that resolves public for the pre-check and private at connect time (DNS
  rebinding, or the reverse) is rejected before a socket opens, so the check
  and the connect cannot diverge. When a name resolves to several allowed
  addresses the first is used; the fetch fails rather than falling back to an
  address that was not checked.
* Redirects are followed manually, at most five, and every hop is re-validated
  (scheme, port, userinfo, destination) before a connection is made.
* The body is streamed and the byte cap (default ``fetch_max_bytes``, 10 MB)
  applies to decoded bytes, so a gzip bomb cannot expand past it; the same cap
  bounds the bytes read from the socket, because producing decoded output
  consumes at least the matching raw input.
* Connect, read, and total timeouts are all ``fetch_timeout_seconds`` (15 s by
  default).
* An optional ``proxy`` keeps the capture egress proxy (D-08) usable. It is
  operator-only: a proxy argument is refused unless it matches the configured
  ``capture_egress_proxy``, and callers must never pass a user-supplied value.
  Destination checks still run first; the proxy endpoint itself is trusted, so
  ``FetchResult.peer_ip`` is the proxy's address in that mode.

The ``allow_cidrs_for_tests`` constructor argument exists only so tests can
fetch from a local server; it is not reachable from settings, which never
carry an allow list.
"""

from __future__ import annotations

import contextlib
import ipaddress
import re
import socket
import ssl
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import anyio
import httpcore
import httpx

from aegis.common.config import Settings, get_settings

DEFAULT_MAX_REDIRECTS = 5

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_METHOD_CHANGING_STATUSES = frozenset({301, 302, 303})
_ALLOWED_SCHEMES = frozenset({"http", "https"})

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]

BLOCKED_NETWORKS: tuple[_IPNetwork, ...] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)

_IPV4_EMBEDDED_NETWORKS: tuple[_IPNetwork, ...] = tuple(
    ipaddress.ip_network(cidr) for cidr in ("::/96", "::ffff:0:0/96", "64:ff9b::/96")
)

_NUMERIC_PART = re.compile(r"\A(?:0[xX][0-9a-fA-F]+|[0-9]+)\Z")
_HTTP_TOKEN = re.compile(r"\A[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_HEADER_VALUE = re.compile(r"\A[\x20-\x7e\t]*\Z")


def _validate_method(method: str) -> None:
    if not _HTTP_TOKEN.match(method):
        raise ValueError("method must be an HTTP token")


def _validate_accept(accept: str | None) -> None:
    if accept is not None and not _HEADER_VALUE.match(accept):
        raise ValueError("accept must be a header value without control characters")


class FetchError(Exception):
    """Raised when a fetch cannot be completed safely."""


class BlockedDestinationError(FetchError):
    """Raised when a URL is not allowed to be fetched."""


class FetchTooLargeError(FetchError):
    """Raised when a response body exceeds the configured cap."""


class TooManyRedirectsError(FetchError):
    """Raised when a response redirects more than the allowed number of times."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A capped, decoded response body with the metadata callers need."""

    final_url: str
    status: int
    headers: httpx.Headers
    body: bytes
    content_type: str | None
    redirects: int
    peer_ip: str | None


@dataclass(frozen=True, slots=True)
class _ProxyEndpoint:
    url: httpcore.URL
    auth: tuple[str, str] | None
    host: str
    port: int


async def _system_resolver(host: str, port: int) -> list[str]:
    """Resolve a hostname with the platform resolver."""

    results = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(result[4][0]) for result in results]


def _parse_integer_part(part: str) -> int | None:
    lowered = part.lower()
    if lowered.startswith("0x"):
        digits, base = lowered[2:], 16
    elif lowered.startswith("0o"):
        digits, base = lowered[2:], 8
    elif len(lowered) > 1 and lowered.startswith("0"):
        digits, base = lowered[1:], 8
    else:
        digits, base = lowered, 10
    if not digits:
        return None
    try:
        value = int(digits, base)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _parse_numeric_host(host: str) -> _IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    numbers: list[int] = []
    for part in parts:
        number = _parse_integer_part(part)
        if number is None:
            return None
        numbers.append(number)
    if len(numbers) == 1:
        value = numbers[0]
    elif len(numbers) == 2:
        if numbers[0] > 0xFF or numbers[1] > 0xFFFFFF:
            return None
        value = (numbers[0] << 24) | numbers[1]
    elif len(numbers) == 3:
        if numbers[0] > 0xFF or numbers[1] > 0xFF or numbers[2] > 0xFFFF:
            return None
        value = (numbers[0] << 24) | (numbers[1] << 16) | numbers[2]
    else:
        if any(number > 0xFF for number in numbers):
            return None
        value = (numbers[0] << 24) | (numbers[1] << 16) | (numbers[2] << 8) | numbers[3]
    try:
        return ipaddress.IPv4Address(value)
    except ValueError:
        return None


def _looks_numeric(host: str) -> bool:
    parts = host.split(".")
    if not 1 <= len(parts) <= 8:
        return False
    if len(parts) == 1:
        return host.isdigit() or host.lower().startswith("0x")
    return all(_NUMERIC_PART.match(part) for part in parts)


def _unwrap_ipv4_embedded(address: _IPAddress) -> list[_IPAddress]:
    candidates: list[_IPAddress] = [address]
    if isinstance(address, ipaddress.IPv6Address):
        for network in _IPV4_EMBEDDED_NETWORKS:
            if address in network:
                embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
                candidates.extend(_unwrap_ipv4_embedded(embedded))
                break
    return candidates


def _port_of(url: httpx.URL) -> int:
    return url.port or (443 if url.scheme == "https" else 80)


def _display(url: httpx.URL) -> str:
    return f"{url.scheme}://{url.host}:{_port_of(url)}"


def _parse_ports(value: str) -> frozenset[int]:
    ports: set[int] = set()
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            port = int(token)
        except ValueError as exc:
            raise ValueError(f"invalid port {token!r} in fetch_allowed_ports") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"port {port} in fetch_allowed_ports is out of range")
        ports.add(port)
    if not ports:
        raise ValueError("fetch_allowed_ports must name at least one port")
    return frozenset(ports)


def _parse_networks(values: Iterable[str]) -> tuple[_IPNetwork, ...]:
    networks: list[_IPNetwork] = []
    for value in values:
        for item in value.split(","):
            token = item.strip()
            if not token:
                continue
            try:
                networks.append(ipaddress.ip_network(token, strict=False))
            except ValueError as exc:
                raise ValueError(f"invalid CIDR {token!r}") from exc
    return tuple(networks)


class _DestinationPolicy:
    """Resolves hosts and decides whether an address may be connected to."""

    def __init__(
        self,
        *,
        resolver: Resolver,
        allowed_ports: frozenset[int],
        blocked_networks: tuple[_IPNetwork, ...],
        allowed_networks: tuple[_IPNetwork, ...] = (),
    ) -> None:
        self._resolver = resolver
        self._allowed_ports = allowed_ports
        self._blocked = blocked_networks
        self._allowed = allowed_networks

    def check_port(self, port: int) -> None:
        if port not in self._allowed_ports:
            raise BlockedDestinationError(f"port {port} is not allowed")

    def check_address(self, address: _IPAddress) -> None:
        for candidate in _unwrap_ipv4_embedded(address):
            if any(candidate in network for network in self._allowed):
                continue
            if any(candidate in network for network in self._blocked):
                raise BlockedDestinationError(f"destination {candidate} is in a blocked range")

    async def resolve(self, host: str, port: int) -> list[_IPAddress]:
        numeric = _parse_numeric_host(host)
        if numeric is not None:
            return [numeric]
        if _looks_numeric(host):
            raise BlockedDestinationError(f"host {host!r} is not a valid numeric address")
        try:
            raw = await self._resolver(host, port)
        except OSError as exc:
            raise FetchError(f"could not resolve host {host!r}") from exc
        addresses: list[_IPAddress] = []
        for item in raw:
            try:
                address = ipaddress.ip_address(item)
            except ValueError as exc:
                raise FetchError(f"resolver returned an invalid address for host {host!r}") from exc
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise FetchError(f"host {host!r} did not resolve to any address")
        return addresses

    async def check(self, host: str, port: int) -> list[_IPAddress]:
        self.check_port(port)
        addresses = await self.resolve(host, port)
        for address in addresses:
            self.check_address(address)
        return addresses


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connects only to addresses that pass the destination policy."""

    def __init__(self, policy: _DestinationPolicy, *, trusted_endpoint: tuple[str, int] | None = None) -> None:
        self._policy = policy
        self._trusted_endpoint = trusted_endpoint
        self._backend = httpcore.AnyIOBackend()
        self.peer_ip: str | None = None

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if self._trusted_endpoint is not None and (host, port) == self._trusted_endpoint:
            addresses = await self._policy.resolve(host, port)
        else:
            addresses = await self._policy.check(host, port)
        address = addresses[0]
        self.peer_ip = str(address)
        return await self._backend.connect_tcp(
            host=str(address),
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise FetchError("unix domain sockets are not supported")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


_HTTPCORE_ERROR_MAP: dict[type[BaseException], type[httpx.HTTPError]] = {
    httpcore.ConnectTimeout: httpx.ConnectTimeout,
    httpcore.ReadTimeout: httpx.ReadTimeout,
    httpcore.WriteTimeout: httpx.WriteTimeout,
    httpcore.PoolTimeout: httpx.PoolTimeout,
    httpcore.TimeoutException: httpx.TimeoutException,
    httpcore.ConnectError: httpx.ConnectError,
    httpcore.ReadError: httpx.ReadError,
    httpcore.WriteError: httpx.WriteError,
    httpcore.NetworkError: httpx.NetworkError,
    httpcore.ProxyError: httpx.ProxyError,
    httpcore.UnsupportedProtocol: httpx.UnsupportedProtocol,
    httpcore.LocalProtocolError: httpx.LocalProtocolError,
    httpcore.RemoteProtocolError: httpx.RemoteProtocolError,
    httpcore.ProtocolError: httpx.ProtocolError,
}


def _mapped_error(exc: Exception) -> type[httpx.HTTPError] | None:
    for core_type, http_type in _HTTPCORE_ERROR_MAP.items():
        if isinstance(exc, core_type):
            return http_type
    return None


@contextlib.contextmanager
def _translate_httpcore_errors() -> Iterator[None]:
    try:
        yield
    except FetchError:
        raise
    except Exception as exc:
        mapped = _mapped_error(exc)
        if mapped is None:
            raise
        raise mapped(str(exc)) from exc


class _AsyncResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: AsyncIterable[bytes]) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        with _translate_httpcore_errors():
            async for part in self._stream:
                yield part

    async def aclose(self) -> None:
        aclose = getattr(self._stream, "aclose", None)
        if aclose is not None:
            await aclose()


class _PinnedTransport(httpx.AsyncBaseTransport):
    """An ``httpx`` transport over a pinned ``httpcore`` connection pool."""

    def __init__(self, backend: _PinnedNetworkBackend, *, proxy: _ProxyEndpoint | None = None) -> None:
        ssl_context = ssl.create_default_context()
        limits = httpx.Limits()
        pool_options: dict[str, Any] = {
            "ssl_context": ssl_context,
            "max_connections": limits.max_connections,
            "max_keepalive_connections": limits.max_keepalive_connections,
            "keepalive_expiry": limits.keepalive_expiry,
            "http1": True,
            "http2": False,
            "retries": 0,
            "network_backend": backend,
        }
        self._pool: httpcore.AsyncConnectionPool | httpcore.AsyncHTTPProxy
        if proxy is None:
            self._pool = httpcore.AsyncConnectionPool(**pool_options)
        else:
            self._pool = httpcore.AsyncHTTPProxy(proxy_url=proxy.url, proxy_auth=proxy.auth, **pool_options)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _translate_httpcore_errors():
            core_response = await self._pool.handle_async_request(core_request)
        stream = core_response.stream
        assert isinstance(stream, AsyncIterable)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_AsyncResponseStream(stream),
            extensions=core_response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


class SafeFetcher:
    """Fetch untrusted URLs with the SSRF protections described in the module docstring."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        resolver: Resolver | None = None,
        allow_cidrs_for_tests: Iterable[str] = (),
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self._settings = settings or get_settings()
        self._max_bytes = self._settings.fetch_max_bytes
        self._timeout = self._settings.fetch_timeout_seconds
        self._user_agent = self._settings.fetch_user_agent
        self._max_redirects = max_redirects
        self._client_timeout = httpx.Timeout(
            connect=self._timeout,
            read=self._timeout,
            write=self._timeout,
            pool=self._timeout,
        )
        self._policy = _DestinationPolicy(
            resolver=resolver or _system_resolver,
            allowed_ports=_parse_ports(self._settings.fetch_allowed_ports),
            blocked_networks=BLOCKED_NETWORKS + _parse_networks((self._settings.fetch_extra_blocked_cidrs,)),
            allowed_networks=_parse_networks(allow_cidrs_for_tests),
        )

    async def fetch(
        self,
        url: str,
        *,
        max_bytes: int | None = None,
        accept: str | None = None,
        method: str = "GET",
        proxy: str | None = None,
    ) -> FetchResult:
        """Fetch ``url``, following at most five redirects.

        ``max_bytes`` defaults to ``fetch_max_bytes``. ``proxy`` is an
        operator-only ``http``/``https`` proxy endpoint and must match
        ``capture_egress_proxy``; never pass a user-supplied value.
        """

        limit = self._max_bytes if max_bytes is None else max_bytes
        if limit <= 0:
            raise ValueError("max_bytes must be positive")
        _validate_method(method)
        _validate_accept(accept)
        target = self._parse_url(url)
        headers = {
            "user-agent": self._user_agent,
            "accept": accept or "*/*",
            "accept-encoding": "identity",
        }
        redirects = 0
        try:
            with anyio.fail_after(self._timeout):
                while True:
                    await self._policy.check(target.raw_host.decode("ascii"), _port_of(target))
                    proxy_endpoint = self._resolve_proxy(proxy)
                    backend = _PinnedNetworkBackend(
                        self._policy,
                        trusted_endpoint=None if proxy_endpoint is None else (proxy_endpoint.host, proxy_endpoint.port),
                    )
                    transport = _PinnedTransport(backend, proxy=proxy_endpoint)
                    async with httpx.AsyncClient(
                        transport=transport,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=self._client_timeout,
                    ) as client:
                        request = client.build_request(method, target, headers=headers)
                        response = await client.send(request, stream=True)
                        location = response.headers.get("location")
                        if response.status_code in _REDIRECT_STATUSES and location:
                            previous_status = response.status_code
                            joined = response.url.join(location)
                            await response.aclose()
                            if redirects >= self._max_redirects:
                                raise TooManyRedirectsError(
                                    f"more than {self._max_redirects} redirects while fetching {_display(target)}"
                                )
                            redirects += 1
                            target = self._validate_target(joined)
                            if previous_status in _METHOD_CHANGING_STATUSES and method not in {"GET", "HEAD"}:
                                method = "GET"
                            continue
                        body = await self._read_body(response, limit)
                        return FetchResult(
                            final_url=str(response.url),
                            status=response.status_code,
                            headers=response.headers,
                            body=body,
                            content_type=response.headers.get("content-type"),
                            redirects=redirects,
                            peer_ip=backend.peer_ip,
                        )
        except TimeoutError as exc:
            raise FetchError(f"fetch of {_display(target)} timed out") from exc
        except FetchError:
            raise
        except httpx.HTTPError as exc:
            raise FetchError(f"fetch of {_display(target)} failed: {exc}") from exc
        except Exception as exc:
            raise FetchError(f"fetch of {_display(target)} failed: {type(exc).__name__}") from exc

    def _parse_url(self, url: str) -> httpx.URL:
        try:
            target = httpx.URL(url)
        except httpx.InvalidURL as exc:
            raise FetchError("invalid URL") from exc
        return self._validate_target(target)

    def _validate_target(self, target: httpx.URL) -> httpx.URL:
        if target.scheme not in _ALLOWED_SCHEMES:
            raise BlockedDestinationError(f"scheme {target.scheme!r} is not allowed")
        if target.username or target.password:
            raise BlockedDestinationError(f"userinfo is not allowed in {_display(target)}")
        if not target.raw_host:
            raise BlockedDestinationError("URL has no host")
        self._policy.check_port(_port_of(target))
        return target

    def _parse_proxy(self, proxy: str) -> _ProxyEndpoint:
        try:
            url = httpx.URL(proxy)
        except httpx.InvalidURL as exc:
            raise FetchError("invalid proxy URL") from exc
        if url.scheme not in _ALLOWED_SCHEMES or not url.raw_host:
            raise FetchError("proxy URL must be an http or https URL with a host")
        host = url.raw_host.decode("ascii")
        port = _port_of(url)
        core_url = httpcore.URL(scheme=url.raw_scheme, host=url.raw_host, port=port)
        auth = (url.username, url.password) if (url.username or url.password) else None
        return _ProxyEndpoint(url=core_url, auth=auth, host=host, port=port)

    def _resolve_proxy(self, proxy: str | None) -> _ProxyEndpoint | None:
        if proxy is None:
            return None
        endpoint = self._parse_proxy(proxy)
        configured = self._settings.capture_egress_proxy
        if not configured:
            raise FetchError("a proxy can only be used when capture_egress_proxy is configured")
        allowed = self._parse_proxy(configured)
        if (endpoint.url.scheme, endpoint.host, endpoint.port) != (allowed.url.scheme, allowed.host, allowed.port):
            raise FetchError("proxy must match capture_egress_proxy")
        return allowed

    async def _read_body(self, response: httpx.Response, limit: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in response.aiter_bytes():
                if len(chunk) > limit - total:
                    raise FetchTooLargeError(f"response body exceeds {limit} bytes")
                total += len(chunk)
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)
