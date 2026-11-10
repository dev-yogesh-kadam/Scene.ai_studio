"""The API's hardening pass (November 2026): routes that had no test, object-level checks between two users, input
checks, clean JSON errors and paging."""

import json
import time

from test_mobile_api import ADA, item, signed_in

BOB = {"email": "bob@example.com", "password": "correct horse"}


# ---------------------------------------------------------------- the share page's look (CSP: no inline <style>)

def test_the_share_page_takes_its_look_from_a_file_the_policy_allows(client):
    ada = signed_in(client)
    made = item(client, ada["id"], "Fox")
    link = client.post("/api/library/{}/share".format(made)).json()
    client.cookies.clear()
    page = client.get(link["path"])
    assert page.status_code == 200 and "<style" not in page.text and 'style="' not in page.text
    assert '<link rel="stylesheet" href="/s/share.css">' in page.text
    assert "style-src 'self'" in page.headers["content-security-policy"]   # the policy that dropped the inline <style>
    css = client.get("/s/share.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert "video,img{" in css.text and "{{" not in css.text
