"""What browsers report (api/client_errors.py): errors, rejections and Web Vitals from signed-in users only, checked,
limited, and read by the console's System section."""

from test_api import console, register


def test_an_error_and_vitals_are_kept_and_the_console_reads_them(client):
    register(client)
    sent = client.post("/api/client-errors", json={"app": "studio", "kind": "error", "message": "x is undefined",
                                                  "stack": "at Home (home.js:1)", "page": "/home", "build": "123"})
    assert sent.status_code == 204
    for value in (1200, 1800, 5200):
        client.post("/api/client-errors", json={"app": "phone", "kind": "vital", "message": "LCP", "value": value, "page": "/m/"})
    client.post("/api/client-errors", json={"app": "studio", "kind": "vital", "message": "CLS", "value": 0.02, "page": "/"})
    seen = console(client).get("/api/admin/client-errors").json()
    assert [(e["kind"], e["message"], e["page"], e["build"]) for e in seen["errors"]] == [("error", "x is undefined", "/home", "123")]
    assert seen["errors"][0]["email"] and seen["errors"][0]["stack"].startswith("at Home")
    vitals = {v["name"]: v for v in seen["vitals"]}
    assert vitals["LCP"]["count"] == 3 and vitals["LCP"]["p75"] == 5200 and vitals["LCP"]["good"] == round(2 / 3, 3)
    assert vitals["CLS"]["count"] == 1 and vitals["INP"]["count"] == 0 and vitals["INP"]["p75"] is None


def test_reports_are_checked_signed_in_and_limited(client):
    assert client.post("/api/client-errors", json={"app": "studio", "kind": "error", "message": "x"}).status_code == 401
    register(client)
    assert client.post("/api/client-errors", json={"app": "desktop", "kind": "error"}).status_code == 400
    assert client.post("/api/client-errors", json={"app": "studio", "kind": "vital", "message": "FID", "value": 3}).status_code == 400
    assert client.post("/api/client-errors", json={"app": "studio", "kind": "vital", "message": "LCP", "value": "fast"}).status_code == 400
    long = client.post("/api/client-errors", json={"app": "studio", "kind": "rejection", "message": "m" * 9000, "stack": "s" * 9000})
    assert long.status_code == 204
    kept = console(client).get("/api/admin/client-errors").json()["errors"][0]
    assert (len(kept["message"]), len(kept["stack"])) == (500, 4000)
    answers = [client.post("/api/client-errors", json={"app": "studio", "kind": "error", "message": str(n)}).status_code for n in range(40)]
    assert 429 in answers   # at most 30 a minute


def test_the_console_read_is_for_admins_only(client):
    register(client)
    assert client.get("/api/admin/client-errors").status_code == 404   # the studio's port has no admin routes
