"""Bringing a file in from a link (fetch.py, POST /api/library/import): what is fetched, and what is refused."""

import asyncio

import httpx
import pytest

from scene import fetch
from test_api import register

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("url", ["http://127.0.0.1/a.png", "http://10.0.0.5/a.png", "http://192.168.1.4/a.png", "http://169.254.169.254/latest",
                                 "http://[::1]/a.png", "http://[::ffff:127.0.0.1]/a.png", "http://100.123.221.34:8188/view"])
def test_private_addresses_are_never_fetched(url):
    with pytest.raises(fetch.FetchError, match="not a public address"):
        run(fetch._check_host(url))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a.png", "http://user:pw@example.com/a.png", "nothing"])
def test_only_plain_web_links(url):
    with pytest.raises(fetch.FetchError):
        run(fetch._check_host(url))


def served(pages, monkeypatch):
    """A client whose web is `pages` (url -> response); every host counts as public except "internal"."""
    async def check(url):
        if "internal" in url:
            raise fetch.FetchError("internal is not a public address: links into a private network are not fetched.")
    monkeypatch.setattr(fetch, "_check_host", check)
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pages[str(request.url)]), follow_redirects=False)


def test_a_picture_is_fetched_and_a_page_is_not(monkeypatch):
    client = served({"https://cdn.example.com/maya.png": httpx.Response(200, content=PNG),
                     "https://example.com/page": httpx.Response(200, content=b"<html>hi</html>", headers={"content-type": "image/png"})}, monkeypatch)
    data, kind, final = run(fetch.fetch("https://cdn.example.com/maya.png", client))
    assert (data, kind, final) == (PNG, "image", "https://cdn.example.com/maya.png")
    with pytest.raises(fetch.FetchError, match="not an image"):   # what the server says it is does not count
        run(fetch.fetch("https://example.com/page", client))
    assert fetch.filename_for("https://cdn.example.com/x/Maya%20sheet", "image") == "Maya%20sheet.png"
    assert fetch.filename_for("https://cdn.example.com/x/clip.mov", "video") == "clip.mov"


def test_a_redirect_into_the_private_network_is_refused(monkeypatch):
    client = served({"https://example.com/a.png": httpx.Response(302, headers={"location": "http://internal/secret.png"}),
                     "http://internal/secret.png": httpx.Response(200, content=PNG)}, monkeypatch)
    with pytest.raises(fetch.FetchError, match="not a public address"):
        run(fetch.fetch("https://example.com/a.png", client))
    loop = {"https://example.com/loop": httpx.Response(302, headers={"location": "/loop"})}
    with pytest.raises(fetch.FetchError, match="redirected"):
        run(fetch.fetch("https://example.com/loop", served(loop, monkeypatch)))


def test_too_large_is_refused_as_it_streams(monkeypatch):
    monkeypatch.setattr(fetch, "MAX_BYTES", 100)
    client = served({"https://example.com/big.png": httpx.Response(200, content=PNG + b"\x00" * 200)}, monkeypatch)
    with pytest.raises(fetch.FetchError, match="larger"):
        run(fetch.fetch("https://example.com/big.png", client))


def test_the_import_endpoint_files_the_link_in_the_library(client, monkeypatch):
    register(client)

    async def fake_fetch(url, client=None):
        if "bad" in url:
            raise fetch.FetchError("The link answered 404.")
        return PNG, "image", url
    monkeypatch.setattr(fetch, "fetch", fake_fetch)
    made = client.post("/api/library/import", json={"url": "https://cdn.example.com/kabir_sheet.png", "name": "Kabir sheet"}).json()
    assert (made["kind"], made["name"], made["workflow"]) == ("image", "Kabir sheet", "upload/link")
    assert made["settings"]["source"] == "https://cdn.example.com/kabir_sheet.png"
    assert client.get(f"/api/library/{made['id']}/file").content == PNG
    assert client.post("/api/library/import", json={"url": "https://cdn.example.com/bad.png"}).status_code == 400
    assert client.post("/api/library/import", json={}).status_code == 400


def test_the_agent_brings_in_a_link_from_the_chat(client, monkeypatch):
    from test_agent_shots import hosted
    register(client)

    async def fake_fetch(url, client=None):
        return PNG, "image", url
    monkeypatch.setattr(fetch, "fetch", fake_fetch)
    seen = hosted(monkeypatch, client, {"tool": "import_url", "text": "https://cdn.example.com/emma.png", "query": "emma (base)"},
                  {"tool": "finish", "reply": "ok", "steps": []})
    plan = client.post("/api/agent/plan", json={"instruction": "here is emma: https://cdn.example.com/emma.png"}).json()
    told = [m["content"] for m in seen[-1] if m["role"] == "user"]
    assert any('"name": "emma (base)"' in t and '"item": ' in t for t in told)
    assert any(e.get("text") == "Brought in “emma (base)” from a link" for e in plan["activity"])


# ---------------------------------------------------------------- the guard's gaps (hardening, Nov 2026)

@pytest.mark.parametrize("address", ["::127.0.0.1", "::7f00:1", "64:ff9b::7f00:1", "64:ff9b::a00:5", "::ffff:0:7f00:1",
                                     "fec0::1", "fe80::1%12", "fd12:3456::1", "::", "0.0.0.0", "100.64.0.1", "::ffff:100.123.221.34"])
def test_ipv6_forms_of_a_private_address_are_private(address):
    assert not fetch._public(address)


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700::1111", "::ffff:8.8.8.8", "64:ff9b::808:808"])
def test_public_addresses_stay_public(address):
    assert fetch._public(address)


def a_server(answer):
    """A web server on this machine (a private address): (its port, the requests it was sent)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def test_a_name_that_rebinds_to_a_private_address_after_the_check_reaches_nothing(monkeypatch):
    server, seen = a_server(PNG)
    answers = iter(["93.184.215.14"])   # public when checked, then this machine when the connection is made

    async def resolve(host, port):
        return [next(answers, "127.0.0.1")]

    monkeypatch.setattr(fetch, "_resolve", resolve)
    try:
        with pytest.raises(fetch.FetchError, match="not a public address"):
            run(fetch.fetch("http://rebind.example:{}/a.png".format(server.server_port)))
        from scene import web
        answers = iter(["93.184.215.14"])
        with pytest.raises(web.WebError, match="not a public address"):
            run(web.page("http://rebind.example:{}/a.png".format(server.server_port)))
    finally:
        server.shutdown()
    assert seen == []   # not a byte was sent to it


def test_the_connection_goes_to_the_address_that_was_checked(monkeypatch):
    server, seen = a_server(PNG)

    async def resolve(host, port):   # pinned.example exists only here: the HTTP library never looks it up itself
        return ["127.0.0.1"] if host == "pinned.example" else []

    monkeypatch.setattr(fetch, "_resolve", resolve)
    monkeypatch.setattr(fetch, "_public", lambda address: True)   # this once, the machine itself counts as public
    try:
        data, kind, _ = run(fetch.fetch("http://pinned.example:{}/a.png".format(server.server_port)))
    finally:
        server.shutdown()
    assert (data, kind, seen) == (PNG, "image", ["/a.png"])


def test_no_proxy_or_netrc_of_the_machine_is_used():
    client = fetch.public_client({})
    try:
        assert client.trust_env is False
    finally:
        run(client.aclose())


def test_a_slow_drip_is_stopped_by_the_deadline(monkeypatch):
    async def drip():
        yield PNG
        while True:
            await asyncio.sleep(0.05)
            yield b"\x00"

    monkeypatch.setattr(fetch, "DEADLINE", 0.5)
    client = served({"https://example.com/slow.png": httpx.Response(200, content=drip())}, monkeypatch)
    with pytest.raises(fetch.FetchError, match="took longer"):
        run(fetch.fetch("https://example.com/slow.png", client))


def test_a_page_with_a_slow_drip_or_an_odd_charset_is_handled(monkeypatch):
    from scene import web

    async def drip():
        yield b"<html><title>x</title>"
        while True:
            await asyncio.sleep(0.05)
            yield b" "

    monkeypatch.setattr(web, "DEADLINE", 0.5)
    pages = {"https://example.com/slow": httpx.Response(200, content=drip(), headers={"content-type": "text/html"}),
             "https://example.com/odd": httpx.Response(200, content=b"<html><title>Odd</title></html>",
                                                       headers={"content-type": "text/html; charset=no-such-charset"})}
    client = served(pages, monkeypatch)
    with pytest.raises(web.WebError, match="took longer"):
        run(web.page("https://example.com/slow", client))
    assert run(web.page("https://example.com/odd", client))["title"] == "Odd"
