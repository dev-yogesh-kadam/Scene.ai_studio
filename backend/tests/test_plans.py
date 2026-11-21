"""The agent's plans run by the server (plans.py, docs/r1-plan-runner-design.md): the price reserved once at approval,
steps drawing from it, failed steps refunded, the rest given back once, stop, resume, a restart, the cut's takes."""

import asyncio
import json
import time

import pytest

from scene.db import offload
from scene.jobs import JobError
from scene.plans import PlanRunner

USER = {"name": "Ada", "email": "ada@example.com", "password": "correct horse"}
IMAGE = "image/@nano_banana_pro"   # a picture model of the test provider (studio_models.py)
PROMPT = "2:value"                 # its prompt (the provider form's first node)
# A picture of one pixel: what the stand-in render files in the library.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8cfc0f0"
                    "1f0005000201e5270ddb0000000049454e44ae426082")


@pytest.fixture
def studio(client, monkeypatch):
    """The studio with a render that files a picture in place of the provider's (or fails, or waits, as a test says),
    and references kept without storing them."""
    manager = client.app.state.jobs
    client.hold = {}      # job name -> asyncio.Event the render waits for
    client.failing = set()   # job names whose render fails

    client.started = []   # job names, in the order their renders started

    async def render(job):
        client.started.append(job["name"])
        if job["name"] in client.hold:
            await client.hold[job["name"]].wait()
        if job["name"] in client.failing:
            raise JobError("The render failed.")
        folder, stem = await offload(manager._target, job)   # as the real render does: off the event loop
        target = folder / (stem + ".png")
        target.write_bytes(PNG)
        await offload(manager._record, job, "image", target, {})

    monkeypatch.setattr(manager, "_run", render)
    from scene.api import library
    async def reference(store, filename, data, db=None, user_id=None):
        return "ref_" + filename
    monkeypatch.setattr(library, "keep_reference", reference)
    client.post("/api/auth/register", json=USER)
    return client


def step(name, **extra):
    return {"name": name, "kind": "image", "settings": {"workflow": IMAGE, "name": name, "values": {PROMPT: "A lighthouse at dusk"}}, **extra}


def balance(client):
    return client.get("/api/auth/me").json()["credits"]


def wait_for(client, plan_id, states=("done", "failed", "stopped"), seconds=20):
    until = time.time() + seconds
    while time.time() < until:
        plan = client.get("/api/agent/plans/{}".format(plan_id)).json()
        if plan["state"] in states:
            return plan
        time.sleep(0.05)
    raise AssertionError("the plan is still " + plan["state"])


def hold(client, name):
    """The render of job `name` waits until released. The event is made in the app's own loop, and set there."""
    async def make():
        return asyncio.Event()
    client.hold[name] = client.portal.call(make)
    return lambda: client.portal.call(client.hold[name].set)


def test_approve_reserves_once_and_the_steps_draw_from_it(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")], "tab": "agent"}).json()
    assert plan["state"] == "waiting" and plan["total"] > 0
    price, before = plan["total"], balance(studio)
    approved = studio.post("/api/agent/plans/{}/approve".format(plan["id"])).json()
    again = studio.post("/api/agent/plans/{}/approve".format(plan["id"])).json()   # twice: charged once
    assert approved["state"] in ("running", "done") and again["id"] == plan["id"]
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and done["reserved_left"] == 0
    assert balance(studio) == before - price   # the reservation paid for the steps: nothing charged twice
    assert all(s["job"] and s["made"] for s in done["steps"])
    rows = studio.app.state.db.all("SELECT plan_id, plan_step FROM jobs ORDER BY plan_step")
    assert [(r["plan_id"], r["plan_step"]) for r in rows] == [(plan["id"], 0), (plan["id"], 1)]
    events = studio.app.state.db.all("SELECT amount, reason, note FROM credit_events WHERE note LIKE 'Reserved for plan%'")
    assert [(e["amount"], e["reason"]) for e in events] == [(-price, "generation")]


def test_a_failed_step_is_refunded_and_the_rest_given_back_once(studio):
    studio.failing.add("two")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    before = balance(studio)
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "failed" and done["steps"][1]["error"]
    one = plan["total"] // 2
    assert balance(studio) == before - one   # the failed step's job gave its price back, as a single job does
    refunds = studio.app.state.db.all("SELECT amount FROM credit_events WHERE reason = 'refund'")
    assert sum(r["amount"] for r in refunds) == plan["total"] - one


def test_two_plans_on_a_balance_for_one(studio):
    db = studio.app.state.db
    first = studio.post("/api/agent/plans", json={"steps": [step("a")]}).json()
    second = studio.post("/api/agent/plans", json={"steps": [step("b")]}).json()
    db.run("UPDATE users SET credits = ?", (first["total"],))   # enough for one of them
    assert studio.post("/api/agent/plans/{}/approve".format(first["id"])).status_code == 200
    refused = studio.post("/api/agent/plans/{}/approve".format(second["id"]))
    assert refused.status_code == 402 and "needs" in refused.json()["detail"]
    assert studio.get("/api/agent/plans/{}".format(second["id"])).json()["state"] == "waiting"
    wait_for(studio, first["id"])
    assert balance(studio) == 0


def test_stop_leaves_the_rest_unqueued_and_gives_its_price_back(studio):
    release = hold(studio, "one")
    later = step("three", after={"step": 0, "slot": "first_frame"})   # waits for the first step's picture
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two"), later]}).json()
    before = balance(studio)
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    until = time.time() + 10
    while not studio.get("/api/agent/plans/{}".format(plan["id"])).json()["steps"][2]["waiting"]:
        assert time.time() < until
        time.sleep(0.05)
    studio.post("/api/agent/plans/{}/stop".format(plan["id"]))
    release()
    done = wait_for(studio, plan["id"])
    assert done["state"] == "stopped"
    assert [bool(s["job"]) for s in done["steps"]] == [True, True, False]
    each = plan["total"] // 3
    assert balance(studio) == before - 2 * each   # the third step's price came back with the rest of the reservation


def test_resume_reserves_again_for_what_is_left(studio):
    studio.failing.add("one")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two", after={"step": 0, "slot": "x"})]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    studio.failing.discard("one")   # tried again, it is made this time
    resumed = studio.post("/api/agent/plans/{}/resume".format(plan["id"])).json()
    assert resumed["state"] in ("running", "done")
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and all(s["made"] for s in done["steps"])
    counts = studio.app.state.db.all("SELECT status, COUNT(*) AS n FROM jobs WHERE plan_step = 0 GROUP BY status")
    assert {r["status"]: r["n"] for r in counts} == {"failed": 1, "done": 1}   # the failed one, and the new one


def test_a_restart_goes_on_without_queueing_a_step_twice(studio):
    release = hold(studio, "one")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    until = time.time() + 10
    while studio.app.state.db.one("SELECT COUNT(*) AS n FROM jobs")["n"] < 2:
        assert time.time() < until
        time.sleep(0.05)
    # The server restarts: a new runner, on the same database, picks the running plan up.
    restarted = PlanRunner(studio.app.state)
    studio.app.state.jobs.finished.append(restarted.job_ended)
    studio.portal.call(_start, restarted)
    release()
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done"
    counts = studio.app.state.db.all("SELECT plan_step, COUNT(*) AS n FROM jobs WHERE plan_id = ? GROUP BY plan_step", (plan["id"],))
    assert {r["plan_step"]: r["n"] for r in counts} == {0: 1, 1: 1}


async def _start(runner):
    runner.start()


def test_a_step_that_starts_on_another_waits_for_its_picture(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two", after={"step": 0, "slot": "x"})]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done"
    second = studio.app.state.db.one("SELECT settings FROM jobs WHERE plan_step = 1")
    assert json.loads(second["settings"])["parent"] == done["steps"][0]["made"]


def test_a_step_that_waits_does_not_hold_up_the_free_ones_after_it(studio):
    """Shot two starts on shot one; shots three and four start on nothing: they are queued at once, beside shot one,
    not after it is made (the servers run as many at once as their "Jobs at once")."""
    let_go = hold(studio, "one")
    steps = [step("one"), step("two", after={"step": 0, "slot": "x"}), step("three"), step("four")]
    plan = studio.post("/api/agent/plans", json={"steps": steps}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    queued = lambda: {r["plan_step"] for r in studio.app.state.db.all("SELECT plan_step FROM jobs WHERE plan_id = ?", (plan["id"],))}
    end = time.time() + 10
    while queued() != {0, 2, 3} and time.time() < end:
        time.sleep(0.05)
    assert queued() == {0, 2, 3}   # two waits for one; three and four did not
    let_go()
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and all(s["made"] for s in done["steps"])


def test_the_steps_not_made_are_offered_again_with_why_and_their_price(studio):
    """A failed shot, and the one that started on it, come back for approval (GET .../redo): why each was not made and
    what they cost now. Nothing is charged until Make again resumes the plan, and then only they are made."""
    studio.failing.add("two")
    steps = [step("one"), step("two"), step("three", after={"step": 1, "slot": "x"})]
    plan = studio.post("/api/agent/plans", json={"steps": steps}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    before = balance(studio)
    redo = studio.get("/api/agent/plans/{}/redo".format(plan["id"])).json()
    assert [(x["step"], x["name"]) for x in redo["steps"]] == [(1, "two"), (2, "three")]
    assert redo["steps"][0]["reason"] and redo["total"] > 0   # in words its owner reads (errors.for_user)
    assert balance(studio) == before   # only shown
    studio.failing.clear()
    studio.post("/api/agent/plans/{}/resume".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and balance(studio) == before - redo["total"]
    assert studio.started.count("one") == 1 and studio.started.count("two") == 2   # the one made is not made again


def test_the_cut_uses_the_take_that_was_chosen(studio, monkeypatch):
    from scene.api import workspace
    cuts = []

    async def assemble(body, request, user):
        cuts.append(body)
        return {"job": studio.app.state.jobs.add(user["id"], "cut", "edit/assemble", {"clips": body["clips"]}, "", None)}
    monkeypatch.setattr(workspace, "assemble", assemble)
    release = hold(studio, "one")
    cut = {"name": "Cut", "assemble": {"name": "Cut", "steps": [0]}}
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), cut]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    other = studio.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                    "VALUES (1, ?, 'image', 'take 2', 't.png', '{}', '{}', ?)", (IMAGE, time.time()))
    studio.post("/api/agent/plans/{}/choose".format(plan["id"]), json={"step": 0, "item": other})
    release()
    wait_for(studio, plan["id"])
    assert [c["id"] for c in cuts[0]["clips"]] == [other]


def test_a_plan_is_its_owners_only(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one")]}).json()
    studio.post("/api/auth/logout")
    studio.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "another one"})
    for method, path in (("get", ""), ("post", "/approve"), ("post", "/stop"), ("post", "/resume")):
        answer = getattr(studio, method)("/api/agent/plans/{}{}".format(plan["id"], path))
        assert answer.status_code == 404, path
    assert studio.get("/api/agent/plans").json()["plans"] == []


def test_a_plan_needs_steps(studio):
    assert studio.post("/api/agent/plans", json={"steps": []}).status_code == 400
    assert studio.post("/api/agent/plans", json={"steps": "x"}).status_code == 400


def _paid(db, user_id):
    """What the user has paid in all: every charge less every refund."""
    return -sum(r["amount"] for r in db.all("SELECT amount FROM credit_events WHERE user_id = ? AND reason IN ('generation', 'refund')",
                                             (user_id,)))


def test_a_step_retried_on_resume_is_paid_once_and_what_is_still_reserved_is_used_first(studio):
    db = studio.app.state.db
    me = studio.get("/api/auth/me").json()
    studio.failing.add("two")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    each = plan["total"] // 2
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    assert _paid(db, me["id"]) == each   # step one; step two's job was refunded, the rest of the reservation given back
    # Something still reserved for the plan (here, put there by hand) pays for the retry before the balance does.
    db.run("UPDATE agent_plans SET reserved_left = ? WHERE id = ?", (each, plan["id"]))
    before = balance(studio)
    studio.failing.discard("two")
    studio.post("/api/agent/plans/{}/resume".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and done["reserved_left"] == 0
    assert balance(studio) == before   # nothing new was charged: the retry was paid from what was held
    charges = db.all("SELECT amount FROM credit_events WHERE note = ?", ("Reserved for plan {}".format(plan["id"]),))
    assert [c["amount"] for c in charges] == [-plan["total"]]   # one reservation only
    ran = db.all("SELECT cost - credits_refunded AS spent FROM jobs WHERE plan_id = ?", (plan["id"],))
    assert sum(r["spent"] for r in ran) == 2 * each   # each step paid once: the failed job's price came back


def test_the_daily_limit_is_checked_at_approval(studio):
    db = studio.app.state.db
    studio.post("/api/auth/logout")
    bob = studio.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "another one"}).json()
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    db.run("UPDATE users SET daily_cap = ? WHERE id = ?", (plan["total"] - 1, bob["id"]))
    before = balance(studio)
    refused = studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert refused.status_code == 429 and "24 hours" in refused.json()["detail"]
    assert balance(studio) == before   # nothing reserved
    assert studio.get("/api/agent/plans/{}".format(plan["id"])).json()["state"] == "waiting"
    db.run("UPDATE users SET daily_cap = ? WHERE id = ?", (plan["total"], bob["id"]))   # enough for the plan
    assert studio.post("/api/agent/plans/{}/approve".format(plan["id"])).status_code == 200
    assert wait_for(studio, plan["id"])["state"] == "done"   # its steps were not refused by the limit again


def test_a_plan_approved_at_the_same_moment_elsewhere_is_answered_as_it_is(studio, monkeypatch):
    """Two Approves at once: the one that loses the race answers with the plan as the other left it, read on the
    database's threads (it was read on the event loop, which the tests' loop guard refuses)."""
    plan = studio.post("/api/agent/plans", json={"steps": [step("one")]}).json()
    db = studio.app.state.db
    real = db.achange

    async def lost_the_race(sql, params=()):
        return 0 if "SET state = 'running'" in sql else await real(sql, params)
    monkeypatch.setattr(db, "achange", lost_the_race)
    answered = studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert answered.status_code == 200 and answered.json()["id"] == plan["id"] and answered.json()["state"] == "waiting"


def test_a_resume_the_moment_a_step_failed_tries_it_again_before_the_plan_was_told(studio, monkeypatch):
    # The queue tells the plan a job ended (job_ended) only after the job is shown failed, while a step waiting on it
    # sees it fail at once and ends the plan. A resume in between (a quick user, a busy machine) must still try the
    # failed step again, not end the plan failed at once.
    told = PlanRunner._job_ended

    def late(self, job, status):
        time.sleep(0.5)
        return told(self, job, status)
    monkeypatch.setattr(PlanRunner, "_job_ended", late)
    studio.failing.add("one")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two", after={"step": 0, "slot": "x"})]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    studio.failing.discard("one")
    studio.post("/api/agent/plans/{}/resume".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "done"


def test_a_job_that_ends_between_the_plans_look_and_its_wait_is_not_missed(studio, monkeypatch):
    """The race in the plan's wait: the worker counted the open jobs (one left), the job ended and woke the plans, and
    only then did the worker start waiting, clearing the wake. It waited LOOK_EVERY (5 s) for nothing; with several such
    waits a plan could run past the tests' 20 s. Here the job's end is made to land exactly in that gap: the look says
    the job is open, and before the worker waits, the job ends and its wake is delivered. No other wake comes after."""
    from scene import plans
    runner = studio.app.state.plans
    db = runner.db
    real = db.aone
    landed = []

    async def look(sql, params=()):
        found = await real(sql, params)
        if "COUNT(*) AS n FROM jobs WHERE id IN" in sql and not landed:
            landed.append(True)
            # the job ends now, after the look and before the wait, and its wake (from a thread) is delivered
            while (await real("SELECT status FROM jobs WHERE id = ?", (params[0],)))["status"] != "done":
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.3)
            return {"n": 1}         # ...while the look saw it still open
        return found
    monkeypatch.setattr(db, "aone", look)
    monkeypatch.setattr(plans, "LOOK_EVERY", 30)   # a lost wake would now cost 30 s, past the wait below
    plan = studio.post("/api/agent/plans", json={"steps": [step("one")]}).json()
    started = time.time()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    done = wait_for(studio, plan["id"], seconds=10)
    assert landed and done["state"] == "done" and time.time() - started < 10


def test_a_plans_later_shots_keep_its_place_ahead_of_what_was_asked_for_after_it(studio):
    """A plan whose next shot starts on the one being made (queued only once that is made) is not overtaken by a
    video asked for after the plan, in another module: its shots render first. Shot three starts on nothing, so it is
    queued at once and renders before shot two, which waits for shot one. The provider's key makes one job at a time."""
    studio.app.state.db.run("UPDATE provider_keys SET max_concurrent = 1")
    studio.app.state.router.forget()
    release = hold(studio, "one")
    steps = [step("one"), step("two", after={"step": 0, "slot": "x"}), step("three")]
    plan = studio.post("/api/agent/plans", json={"steps": steps}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    until = time.time() + 10
    while "one" not in studio.started and time.time() < until:
        time.sleep(0.02)
    other = studio.post("/api/jobs", data={"settings": json.dumps({"workflow": IMAGE, "name": "other", "values": {PROMPT: "A boat"}})})
    assert other.status_code == 200, other.text
    release()
    assert wait_for(studio, plan["id"])["state"] == "done"
    until = time.time() + 10
    while "other" not in studio.started and time.time() < until:
        time.sleep(0.02)
    assert studio.started == ["one", "three", "two", "other"]


def test_a_steps_price_counts_every_slot_it_fills():
    """Priced as the queue fills it: a model that renders only some resolutions with references (MiniMax H3 Max at
    768p) is priced at the one it will be made at, not at the 480p planned before its cast was added."""
    from scene.plans import filled_slots
    shot = {"uses": [{"slot": "ref_1", "id": 4}, {"slot": "ref_2", "asset": "a1", "cast": True}],
            "start": {"id": 9, "slot": "3:image"}, "after": None}
    assert filled_slots(shot) == {"ref_1", "ref_2", "3:image"}
    assert filled_slots({"after": {"step": 0, "slot": "3:image"}}) == {"3:image"}
