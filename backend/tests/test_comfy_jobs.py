"""A render on ComfyUI, against a fake ComfyUI in Python (no render is ever sent to the render PC): it fails with
ComfyUI's own reason, it is cancelled whether or not ComfyUI answers the cancel, it is given up when ComfyUI no longer
has it (restarted) or when it never finishes, and in every case the credits held for it are given back."""

import time

import httpx
import pytest

from scene import jobs as jobs_module
from test_api import post_job, register


class FakeComfy:
    """What the queue asks a ComfyUI server, answered as told: history(prompt) gives `entry`, holds(prompt) `held`."""

    url = "http://fake-comfy.invalid"

    def __init__(self, entry=None, held=True, down=False, cancel_fails=False):
        self.entry, self.held, self.down, self.cancel_fails = entry, held, down, cancel_fails
        self.queued, self.cancelled = [], []

    def ws_url(self, client_id):
        return "ws://127.0.0.1:9/ws?clientId=" + client_id   # nothing listens: progress is best effort

    async def stats(self):
        if self.down:
            raise httpx.ConnectError("the render PC does not answer")
        return {}

    async def queue(self, prompt, client_id):
        if self.down:
            raise httpx.ConnectError("the render PC does not answer")
        self.queued.append(prompt)
        return "p{}".format(len(self.queued))

    async def history(self, prompt_id):
        return self.entry

    async def holds(self, prompt_id):
        return self.held

    async def cancel(self, prompt_id):
        if self.cancel_fails:
            raise httpx.ConnectError("gone")
        self.cancelled.append(prompt_id)


def until(check, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        found = check()
        if found:
            return found
        time.sleep(0.05)
    return check()


@pytest.fixture
def fake(client, monkeypatch):
    register(client)
    manager = client.app.state.jobs
    monkeypatch.setattr(jobs_module, "POLL", 0.05)
    monkeypatch.setattr(manager, "comfy", FakeComfy())
    monkeypatch.setattr(manager, "pool", None)   # one server: the fake
    return manager


def ended(client, job_id, statuses=("failed", "cancelled", "done")):
    return until(lambda: (lambda r: r if r["status"] in statuses else None)(
        client.app.state.db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))))


def credits(client):
    return client.get("/api/auth/me").json()["credits"]


def test_an_error_on_comfyui_fails_the_job_with_its_reason_and_refunds_it(client, fake):
    fake.comfy.entry = {"status": {"status_str": "error", "completed": False, "messages": [
        ["execution_error", {"node_type": "KSampler", "exception_message": "CUDA out of memory"}]]}}
    before = credits(client)
    job = post_job(client).json()
    row = ended(client, job["id"])
    assert row["status"] == "failed" and "out of memory" in row["error"], row["error"]
    assert fake.comfy.queued and credits(client) == before and row["credits_refunded"] == job["credits"]


def test_a_render_comfyui_no_longer_has_is_given_up_and_refunded(client, fake):
    fake.comfy.held = False   # restarted: neither in its history nor in its queue
    before = credits(client)
    job = post_job(client).json()
    row = ended(client, job["id"])
    assert row["status"] == "failed" and "no longer has the render" in row["error"], row["error"]
    assert credits(client) == before


def test_a_render_that_never_finishes_is_stopped_on_comfyui_and_refunded(client, fake, monkeypatch):
    monkeypatch.setattr(jobs_module, "RENDER_MOST", 0.5)   # held, running, never done
    before = credits(client)
    job = post_job(client).json()
    row = ended(client, job["id"])
    assert row["status"] == "failed" and "had not finished" in row["error"], row["error"]
    assert fake.comfy.cancelled == ["p1"] and credits(client) == before


@pytest.mark.parametrize("cancel_fails", [False, True])
def test_a_cancelled_render_is_taken_off_comfyui_and_refunded(client, fake, cancel_fails):
    fake.comfy.cancel_fails = cancel_fails     # the render PC gone by then: still cancelled, never put back in the queue
    fake.hold_offline = True
    try:
        before = credits(client)
        job = post_job(client).json()
        assert until(lambda: client.app.state.db.one("SELECT status FROM jobs WHERE id = ?", (job["id"],))["status"] == "running")
        until(lambda: fake.comfy.queued)
        assert client.delete("/api/jobs/" + job["id"]).status_code == 200
        row = ended(client, job["id"])
        assert row["status"] == "cancelled" and row["resumes"] == 0
        assert fake.comfy.cancelled == ([] if cancel_fails else ["p1"]) and credits(client) == before
    finally:
        fake.hold_offline = False


def test_a_render_pc_that_never_answers_fails_the_job_and_refunds_it(client, fake):
    fake.comfy.down = True
    before = credits(client)
    job = post_job(client).json()
    row = ended(client, job["id"])
    assert row["status"] == "failed" and "Lost the connection" in row["error"] and credits(client) == before
