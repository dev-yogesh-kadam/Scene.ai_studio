"""Bringing a picture, clip or sound in from a link on another site, for the library (a link in the chat, a row of a
shot tracker).

The server fetches it, so a link must never reach the studio's own network: only http and https, only
public addresses — every address the name resolves to is checked before connecting, again at every redirect, and the
connection itself is made to an address checked in the same breath (public_client: the HTTP library does not look the
name up again, so a name that changes its answer between the check and the connection, DNS rebinding, reaches
nothing), and the address connected to is checked once more before the body is read. No proxy or .netrc of the
machine is used. At most MAX_BYTES, read as it streams, within DEADLINE seconds in all, and the content must be an
image, a video or a sound by its first bytes, whatever the link or the server says it is.
"""

import asyncio
import ipaddress
import socket
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from .references import KINDS, MAX_BYTES
from .security import sniff

REDIRECTS = 3
TIMEOUT = httpx.Timeout(60, connect=10)   # each step: the connection, and each read of the body
DEADLINE = 600                           # seconds a whole download may take (200 MB at a slow 3 Mbit/s): a slow drip ends
EXTENSION = {"image": ".png", "video": ".mp4", "audio": ".mp3"}   # when the link's name has none of its kind


class FetchError(ValueError):
    pass


# IPv6 forms that carry an IPv4 address the network may deliver to: NAT64 (64:ff9b::/96, RFC 6052), the old
# IPv4-compatible ::a.b.c.d, and SIIT's ::ffff:0:a.b.c.d. Python counts them global whatever IPv4 address they hold.
EMBEDDING = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "::/96", "::ffff:0:0:0/96")]
SITE_LOCAL = ipaddress.ip_network("fec0::/10")   # deprecated, still private where it is used; Python counts it global


def _public(address):
    """Whether an address (as getaddrinfo gives it, an IPv6 one perhaps with its %scope) is on the public internet."""
    ip = ipaddress.ip_address(str(address).split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip in SITE_LOCAL:
            return False
        elif any(ip in net for net in EMBEDDING):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


async def _resolve(host, port):
    """Every address a name resolves to (an address given as one is itself)."""
    found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in found))


async def _public_addresses(host, port):
    """The addresses of a name, all of them public, or FetchError."""
    try:
        addresses = await _resolve(host, port)
    except (socket.gaierror, UnicodeError):
        raise FetchError("{} could not be found.".format(host))
    if not addresses or not all(_public(a) for a in addresses):
        raise FetchError("{} is not a public address: links into a private network are not fetched.".format(host))
    return addresses


async def _check_host(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http and https links can be brought in.")
    if parts.username or parts.password:
        raise FetchError("A link with a name and password in it is not fetched.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise FetchError("The link's port is not a number.")
    await _public_addresses(parts.hostname, port)


class _PublicOnly(httpcore.AsyncNetworkBackend):
    """The HTTP library's way to the network, connecting only to public addresses, which it looks up and checks
    itself: the connection goes to the very address that was checked (TLS still names the host)."""

    def __init__(self, inner=None):
        self.inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        problem = None
        for address in await _public_addresses(host, port):
            try:
                return await self.inner.connect_tcp(address, port, timeout=timeout, local_address=local_address,
                                                    socket_options=socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:   # the next address, as a browser would
                problem = error
        raise problem

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise FetchError("Links are fetched from the web only.")

    async def sleep(self, seconds):
        await self.inner.sleep(seconds)


def public_client(headers):
    """An HTTP client that reaches only public addresses (see _PublicOnly), with no redirects followed for it (each is
    checked here), and nothing of the machine's own: no proxy, no .netrc password."""
    transport = httpx.AsyncHTTPTransport(retries=0)
    if not hasattr(transport._pool, "_network_backend"):   # httpx's inside changed: refuse rather than go unguarded
        raise FetchError("The studio's link fetcher needs updating: no link is fetched.")
    transport._pool._network_backend = _PublicOnly()
    return httpx.AsyncClient(transport=transport, timeout=TIMEOUT, follow_redirects=False, trust_env=False, headers=headers)


def _kind(data, url, content_type):
    found = sniff(data)
    if found == "video/audio":   # an MP4-family file: a sound when the link or the server says so
        suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
        return "audio" if suffix in KINDS["audio"] or (content_type or "").startswith("audio/") else "video"
    return found


def filename_for(url, kind, data=b""):
    """A file name for what a link brought: the link's own name, with an extension of its kind. data: the file, whose
    first bytes name the type of a picture whose link names none (an image proxy's "?url=...&output=webp")."""
    name = PurePosixPath(urlsplit(url).path).name or kind
    if PurePosixPath(name).suffix.lower() not in KINDS[kind]:
        head = bytes(data[:12])
        suffix = ".webp" if head[:4] == b"RIFF" and head[8:12] == b"WEBP" else ".jpg" if head.startswith(b"\xff\xd8\xff") else EXTENSION[kind]
        name = (PurePosixPath(name).stem or kind) + (suffix if kind == "image" else EXTENSION[kind])
    return name


async def fetch(url, client=None):
    """The file at a link: (bytes, kind, the link it finally came from). Raises FetchError with the reason."""
    own = client is None
    client = client or public_client({"User-Agent": "Scene.ai importer"})
    try:
        async with asyncio.timeout(DEADLINE):
            return await _download(client, url)
    except TimeoutError:
        raise FetchError("The link took longer than {} s to bring in.".format(DEADLINE))
    except httpx.HTTPError as error:
        raise FetchError("The link could not be fetched: {}".format(type(error).__name__))
    finally:
        if own:
            await client.aclose()


def _length(response):
    """The length a response says it has, 0 when it says none (or nonsense)."""
    try:
        return int(response.headers.get("content-length") or 0)
    except ValueError:
        return 0


async def _download(client, url):
    """fetch() without its client and its time limit."""
    for _ in range(REDIRECTS + 1):
        await _check_host(url)
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            stream = response.extensions.get("network_stream")
            peer = stream.get_extra_info("server_addr") if stream is not None else None
            if peer and not _public(peer[0]):   # the name pointed somewhere else by the time it was connected to
                raise FetchError("The link led into a private network: it was not fetched.")
            if response.status_code != 200:
                raise FetchError("The link answered {}.".format(response.status_code))
            if _length(response) > MAX_BYTES:
                raise FetchError("The file is larger than 200 MB.")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data += chunk
                if len(data) > MAX_BYTES:
                    raise FetchError("The file is larger than 200 MB.")
            kind = _kind(bytes(data[:16]), url, response.headers.get("content-type"))
            if kind not in ("image", "video", "audio"):
                raise FetchError("The link is not an image, a video or a sound (a page, perhaps).")
            return bytes(data), kind, url
    raise FetchError("The link redirected more than {} times.".format(REDIRECTS))
