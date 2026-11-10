"""Reading a page of the web for the agent (its web_fetch tool): a brand's site, an article, a product page, an ad
library's public page. The words of the page come back, with its title and the date it gives, if any, so the agent can
cite it.

Like a link brought into the library (fetch.py), a page is fetched only from public addresses: every address its name
resolves to is checked before connecting and at every redirect, the connection is made to a checked address
(fetch.public_client: no DNS rebinding), and the address connected to is checked before the body is read. Only pages
(HTML or plain text) are read, at most MAX_BYTES of one, within DEADLINE seconds. Claude Code's own WebFetch is not used: it runs on
this machine and would reach the studio's own network.
"""

import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from . import fetch

MAX_BYTES = 3_000_000
DEADLINE = 60          # seconds the whole page may take, redirects and all
TEXT_CHARS = 200_000   # the words of a page that are kept
SKIPPED = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
BLOCKS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header",
          "footer", "nav", "aside", "blockquote", "pre", "table", "figure", "figcaption", "main"}
DATES = ("article:published_time", "og:published_time", "datepublished", "date", "pubdate", "publish-date", "dc.date",
         "article:modified_time", "datemodified")


class WebError(ValueError):
    pass


class _Words(HTMLParser):
    """The words of a page, a line for each block, without its scripts and styles; its title and the date it gives."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping, self.title, self.in_title, self.date = [], 0, "", False, ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        found = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and not self.date:
            name = str(found.get("property") or found.get("name") or found.get("itemprop") or "").lower()
            if name in DATES and found.get("content"):
                self.date = str(found["content"])[:40]
        if tag == "time" and found.get("datetime") and not self.date:
            self.date = str(found["datetime"])[:40]
        if tag in SKIPPED and tag != "head":
            self.skipping += 1
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in SKIPPED and tag != "head" and self.skipping:
            self.skipping -= 1
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skipping:
            self.parts.append(data)


def words_of(html):
    """{"title", "date", "text"} of a page's HTML."""
    reader = _Words()
    try:
        reader.feed(html)
        reader.close()
    except Exception:   # a broken page still gives what was read of it
        pass
    lines = [" ".join(line.split()) for line in "".join(reader.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    return {"title": " ".join(reader.title.split())[:200], "date": reader.date, "text": text[:TEXT_CHARS]}


async def page(url, client=None):
    """The words of the page at a public link: {"url" (where it finally came from), "title", "date", "text"}. Raises
    WebError with the reason."""
    url = str(url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url if url and "://" not in url else url
    own = client is None
    try:
        client = client or fetch.public_client({"User-Agent": "Mozilla/5.0 (compatible; Scene.ai research)"})
        async with asyncio.timeout(DEADLINE):
            return await _read(client, url)
    except TimeoutError:
        raise WebError("The page took longer than {} s to read.".format(DEADLINE))
    except fetch.FetchError as error:   # refused before connecting, or by the connection's own check
        raise WebError(str(error).replace("brought in", "read").replace("fetched", "read"))
    except httpx.HTTPError as error:
        raise WebError("The page could not be fetched: {}".format(type(error).__name__))
    finally:
        if own and client is not None:
            await client.aclose()


async def _read(client, url):
    """page() without its client and its time limit."""
    for _ in range(fetch.REDIRECTS + 1):
        await fetch._check_host(url)
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            stream = response.extensions.get("network_stream")
            peer = stream.get_extra_info("server_addr") if stream is not None else None
            if peer and not fetch._public(peer[0]):
                raise WebError("The link led into a private network: it was not read.")
            if response.status_code != 200:
                raise WebError("The page answered {}.".format(response.status_code))
            kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if kind and not (kind.startswith("text/") or kind in ("application/xhtml+xml", "application/json")):
                raise WebError("The link is not a page ({}): bring a picture, clip or sound in with import_url.".format(kind))
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data += chunk
                if len(data) > MAX_BYTES:
                    break
            try:
                text = bytes(data[:MAX_BYTES]).decode(response.encoding or "utf-8", "replace")
            except LookupError:   # a charset Python does not know
                text = bytes(data[:MAX_BYTES]).decode("utf-8", "replace")
            found = words_of(text) if "html" in kind or "<html" in text[:2000].lower() else {"title": "", "date": "", "text": text[:TEXT_CHARS]}
            return dict(found, url=url)
    raise WebError("The link redirected more than {} times.".format(fetch.REDIRECTS))
