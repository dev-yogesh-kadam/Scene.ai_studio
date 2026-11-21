"""The web app the studio and the admin console serve: apps/web, built into web_dist_dir (the only one since the
classic frontend/ was removed)."""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from conftest import CONSOLE_PAGE, POSTGRES, STUDIO_PAGE, built, empty_postgres
from scene.config import Settings, load_settings
from scene.main import Doors, create_app

def app_with(tmp_path, **settings):
    empty_postgres()
    settings = Settings(database_url=POSTGRES, claude_models="off",
                        storage_dir=str(tmp_path / "storage"), first_account_local=False,
                        **settings)
    return create_app(settings)


@pytest.fixture
def react(tmp_path):
    with TestClient(app_with(tmp_path, web_dist_dir=str(built(tmp_path / "dist")))) as studio:
        studio.console = TestClient(studio.app.state.console)
        yield studio


def test_a_config_from_before_still_starts(tmp_path):
    """A config.json written when there were two web apps names "web_app" and "frontend_dir": they are ignored, and the
    build is served."""
    config = tmp_path / "config.json"
    config.write_text('{"web_app": "classic", "frontend_dir": "frontend", "web_dist_dir": %s}'
                      % json.dumps(str(built(tmp_path / "dist"))), encoding="utf-8")
    settings = load_settings(config)
    assert not hasattr(settings, "web_app") and not hasattr(settings, "frontend_dir")
    settings.storage_dir, settings.claude_models = str(tmp_path / "storage"), "off"
    settings.database_url = POSTGRES
    empty_postgres()
    with TestClient(create_app(settings)) as studio:
        assert studio.get("/home").text == STUDIO_PAGE
        assert studio.get("/assets/js/main.js").status_code == 404   # nothing of the classic app


def test_the_react_studio_serves_its_build_at_every_page_address(react):
    for path in ("/", "/signin", "/home", "/projects", "/canvas", "/canvas/PRJabc/module/MODdef", "/project/PRJabc",
                 "/library", "/create", "/settings", "/guide", "/skills", "/analytics/PRJabc", "/admin"):
        page = react.get(path)
        assert page.status_code == 200 and page.text == STUDIO_PAGE, path
        assert page.headers["cache-control"] == "no-cache", path
    script = react.get("/_app/studio-AbC123.js")
    assert script.status_code == 200 and "immutable" in script.headers["cache-control"]
    assert react.get("/theme.js").text == "// theme"
    assert react.get("/fonts/Archivo-latin.woff2").content == b"font"
    assert react.get("/img/logo.svg").status_code == 200
    # Not the classic page or its files, and nothing outside the build
    assert react.get("/assets/js/main.js").status_code == 404
    assert react.get("/index.html").text == STUDIO_PAGE   # an old address of the page, answered by the new one
    assert react.get("/studio.html").status_code == 404   # the build's own page file is only served at the addresses
    assert react.get("/_app/missing.js").status_code == 404
    assert react.get("/_app/..%2f..%2fconsole%2fconsole.html").status_code == 404


def test_the_react_console_is_served_only_on_its_own_port(react):
    for path in ("/", "/signin", "/users", "/jobs", "/endpoints", "/sessions/SESabc"):
        page = react.console.get(path)
        assert page.status_code == 200 and page.text == CONSOLE_PAGE, path
    assert react.console.get("/_app/console-XyZ789.js").status_code == 200
    assert react.console.get("/theme.js").text == "// theme"
    assert react.console.get("/fonts/Archivo-latin.woff2").status_code == 200
    # The studio's port has none of it
    for path in ("/_app/console-XyZ789.js", "/_APP/Console-XyZ789.js", "/console.html", "/console/console.html",
                 "/assets/js/console/main.js"):
        assert react.get(path).status_code == 404, path


def test_one_server_sends_each_port_to_its_react_site(react):
    doors = Doors(react.app)
    assert "console-XyZ789.js" in TestClient(doors, base_url="http://testserver:8090").get("/").text
    assert "studio-AbC123.js" in TestClient(doors, base_url="http://testserver:8080").get("/").text


def test_the_page_policy_is_the_same_on_every_page_and_both_sites(react, client):
    policy = client.get("/home").headers["content-security-policy"]
    assert "script-src 'self';" in policy and "'unsafe-eval'" not in policy
    assert react.get("/home").headers["content-security-policy"] == policy
    assert react.console.get("/").headers["content-security-policy"] == client.console.get("/").headers["content-security-policy"]
    for header in ("x-frame-options", "x-content-type-options", "referrer-policy", "cross-origin-opener-policy", "permissions-policy"):
        assert react.get("/home").headers[header] == client.get("/home").headers[header], header


def test_the_react_page_version_is_its_last_build(react, tmp_path, monkeypatch):
    """/api/status says the version of the page files, for a tab opened before a new build to offer to reload."""
    import scene.main
    page = tmp_path / "dist" / "studio" / "studio.html"
    assert react.app.state.page_version() == int(page.stat().st_mtime)
    later = time.time() + 100
    os.utime(page, (later, later))
    monkeypatch.setattr(scene.main, "PAGE_LOOK", -1)   # looked at again at once, not after a few seconds
    assert react.app.state.page_version() == int(later)
    assert scene.main._build_version(tmp_path / "nothing", "studio.html") == 0


def test_without_a_build_the_react_pages_say_how_to_build_it(tmp_path):
    with TestClient(app_with(tmp_path, web_dist_dir=str(tmp_path / "nothing"))) as studio:
        page = studio.get("/home")
        assert page.status_code == 503 and "npm run build -w apps/web" in page.text
        assert TestClient(studio.app.state.console).get("/").status_code == 503
        assert studio.get("/api/auth/state").status_code == 200   # the API works all the same
