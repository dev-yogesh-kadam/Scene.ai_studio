"""The studio for phones: a site of its own, built from mobile/ (Expo, for the web) and served at /m/.

A phone that opens one of the studio's pages is sent to the same place on the phone site (a project, a module, the
library...). Tablets and computers get the full studio. Someone who wants the full studio on their phone opens any
page with ?desktop=1 (the phone site's Account has the link): a cookie remembers it until they open /m/ again."""

import re

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .db import as_everyone

BASE = "/m"
DESKTOP = "scene_desktop"   # set: this browser chose the full studio
# A phone, not a tablet: iPads and Android tablets (no "Mobile" in their name) get the full studio.
PHONE = re.compile(r"iPhone|iPod|Android.*Mobile|Mobile.*Firefox|Windows Phone|BlackBerry|Opera Mini|IEMobile", re.I)
# The studio's pages and where each is on the phone site.
SAME = {"/": "/", "/index.html": "/", "/home": "/", "/projects": "/projects", "/library": "/library", "/skills": "/skills",
        "/create": "/create", "/settings": "/account", "/signin": "/login", "/signup": "/login"}
PLACE = re.compile(r"^/(canvas|project|analytics)/([A-Za-z0-9]+)(?:/module/([A-Za-z0-9]+))?")
STUDIO_PAGES = re.compile(r"^/(|index\.html|home|projects|library|skills|create|settings|signin|signup|canvas|project|analytics|guide)(/.*)?$")


def is_phone(request: Request):
    return bool(PHONE.search(request.headers.get("user-agent", "")))


def _place(db, path):
    """Where a studio address with a project's or module's id (PRJ..., MOD...) is on the phone site."""
    found = PLACE.match(path)
    if not found:
        return None
    kind, project_ref, module_ref = found.groups()
    with as_everyone():
        row = db.one("SELECT id FROM projects WHERE ref = ?", (module_ref or project_ref,))
    if not row:
        return "/projects"
    if kind == "project" and not module_ref:
        return "/project/{}".format(row["id"])
    return "/module/{}".format(row["id"])   # a canvas: the module, or the project's own canvas


def install(app, settings):
    site = settings.path("mobile_site_dir").resolve()

    @app.middleware("http")
    async def phones_to_the_phone_site(request: Request, call_next):
        path = request.url.path
        if request.method != "GET" or not STUDIO_PAGES.match(path):
            return await call_next(request)
        if request.query_params.get("desktop") == "1":   # the full studio, chosen on a phone: remembered for a year
            response = await call_next(request)
            response.set_cookie(DESKTOP, "1", max_age=365 * 86400, samesite="lax")
            return response
        if not is_phone(request) or request.cookies.get(DESKTOP) or not (site / "index.html").is_file():
            return await call_next(request)
        target = SAME.get(path) or _place(request.app.state.db, path) or "/"
        return RedirectResponse(BASE + target, status_code=302)

    def index():
        if not (site / "index.html").is_file():
            return HTMLResponse("<!doctype html><meta name=viewport content='width=device-width'><body style='font:16px system-ui;"
                                "padding:24px'>The phone site isn't built yet. On the studio PC, run <code>npm run build</code> in "
                                "<code>mobile/</code>, then reload. <a href='/?desktop=1'>Open the full studio</a></body>", status_code=503)
        response = FileResponse(site / "index.html")
        response.delete_cookie(DESKTOP)   # opening the phone site again ends the choice of the full studio
        return response

    @app.get(BASE, include_in_schema=False)
    @app.get(BASE + "/", include_in_schema=False)
    async def phone_home():
        return index()

    @app.get(BASE + "/{path:path}", include_in_schema=False)
    async def phone_file(path: str):
        """A file of the built site, or, for any other address under /m/ (a screen: /m/module/12), the site itself,
        which shows the screen."""
        target = (site / path).resolve()
        if target.is_relative_to(site) and target.is_file():
            hashed = "/_expo/static/" in "/" + path   # the built scripts have their content's hash in their names
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"} if hashed else None)
        return index()
