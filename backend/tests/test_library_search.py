"""The library's search (GET /api/library?q=, and the phone's): full-text search over an item's name, summary, workflow
and prompt, every word needed, each as the start of a word there; and a name found though a letter or two are wrong
(migration 0009). The same route and the same answer as the LIKE search it replaced."""

import json
import time

from test_api import register

ITEMS = [   # name, workflow, summary, prompt
    ("Sunset beach", "image/image_t2i_flux2_dev", "", "a slow dolly over wet neon streets at night"),
    ("Chai stall", "video/h3_all_in_one", "Dawn in a Mumbai lane", "an old chai seller lights his stove"),
    ("Portrait", "image/image_sdxl_simple", "", "warm rim light on her face, rain on the glass"),
]


def fill(client, user_id):
    now = time.time()
    for n, (name, workflow, summary, prompt) in enumerate(ITEMS):
        client.app.state.db.run(
            "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)",
            (user_id, workflow, workflow.split("/")[0], name, "f{}.png".format(n), summary,
             json.dumps({"workflow": workflow, "values": {"5:text": prompt}, "prompt": prompt}), now + n))


def found(client, q, **params):
    answer = client.get("/api/library", params=dict(q=q, **params))
    assert answer.status_code == 200
    return [i["name"] for i in answer.json()["items"]]


def test_words_of_the_prompt_name_summary_and_workflow_are_found(client):
    me = register(client)
    fill(client, me["id"])
    assert found(client, "neon") == ["Sunset beach"]                  # the prompt
    assert found(client, "mumbai") == ["Chai stall"]                  # the summary, any case
    assert found(client, "flux2") == ["Sunset beach"]                 # a part of the workflow's name
    assert found(client, "portrait") == ["Portrait"]                  # the name
    assert found(client, "rain glass") == ["Portrait"]                # every word, anywhere in it
    assert found(client, "rain neon") == []                           # every word is needed
    assert found(client, "") == ["Portrait", "Chai stall", "Sunset beach"]   # no words: everything, newest first


def test_a_word_is_found_from_its_start_and_a_name_with_a_letter_wrong(client):
    me = register(client)
    fill(client, me["id"])
    assert found(client, "sta") == ["Chai stall"]                     # stall, stove: as it is being typed
    assert found(client, "Sunst beach") == ["Sunset beach"]           # a letter left out of the name
    assert found(client, "Portriat") == ["Portrait"]                  # two letters the wrong way round
    assert found(client, "!!!") == ["Portrait", "Chai stall", "Sunset beach"]   # no word in it: nothing to search for


def test_the_answer_is_as_it_was(client):
    me = register(client)
    fill(client, me["id"])
    page = client.get("/api/library", params={"q": "neon", "limit": 10}).json()
    assert set(page) == {"items", "next_cursor"} and page["next_cursor"] is None
    item = page["items"][0]
    assert "search" not in item and isinstance(item["settings"], dict) and item["settings"]["prompt"].startswith("a slow")
    assert "search" not in client.get("/api/library/{}".format(item["id"])).json()
    phone = client.get("/api/mobile/library", params={"q": "chai"}).json()
    assert [i["name"] for i in phone["items"]] == ["Chai stall"]
