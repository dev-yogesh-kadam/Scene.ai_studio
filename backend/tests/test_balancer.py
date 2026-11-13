"""The load balancer (balancer.py): each waiting render goes to a server that can do it and has a slot free.

A server's "Workflows" (endpoints.models) claim workflows for it alone; the others take what no server claims, when they
have its nodes. "Jobs at once" (endpoints.slots) is how many renders a server runs together. A render no server can do
fails at once; one that has to wait never holds up the renders behind it that another server can do. Every graph is
sent with who and where it is from (extra_data), which the generation server logs and limits by."""

import asyncio
import json
import time

import httpx
import pytest

from scene import balancer, endpoints, errors, generation_models
from scene.comfy.client import ComfyError
from scene.references import keep_reference
from scene import jobs as jobs_module
from scene import media
from scene.balancer import ComfyPool
from scene.comfy import workflows
from test_api import console, register
from test_comfy_jobs import FakeComfy, credits, ended, until

ZORO, ZORO2, GEN, GEN2 = "http://zoro:8188", "http://zoro2:8188", "http://gen:8189", "http://gen2:8189"
FLUX = "image/image_t2i_flux3_klein"
H3_MAX = "video/generation_video"   # the generation server's video models (MiniMax H3 Max by default)
SAMPLER = frozenset({"KSampler", "SaveImage"})


def pool_of(*rows, nodes=None):
    """A pool of these servers (endpoints rows, each {"name", "url", ...}) without a database. nodes: url -> the node
    classes it has, or None for a server whose nodes are not known; a server left out has every node."""
    pool = ComfyPool.__new__(ComfyPool)
    pool.db, pool.fallback, pool.clients, pool.busy, pool.reading = None, "", {}, {}, {}
    pool.main = type("Main", (), {"url": rows[0]["url"]})()
    pool.rows = [dict({"kind": "comfy", "active": 1, "models": "", "slots": 1, "id": i + 1}, **r) for i, r in enumerate(rows)]
    pool.nodes = {r["url"]: (None, time.time()) for r in pool.rows}   # asked just now: not asked again
    pool.nodes.update({url: (None if n is None else frozenset(n), time.time()) for url, n in (nodes or {}).items()})
    return pool


def place(pool, workflow_id, needs=frozenset(), answers=None):
    return asyncio.run(pool.place(workflow_id, needs, answers))


ZORO_ROW = {"name": "Zoro", "url": ZORO}
GEN_ROW = {"name": "Generation server", "url": GEN, "models": "generation_*", "slots": 4}


# ---------------------------------------------------------------- what each server can do


def test_patterns_match_the_whole_id_or_the_file_name():
    assert balancer.matches(["generation_*"], H3_MAX)
    assert balancer.matches(["video/generation_*"], H3_MAX)
    assert not balancer.matches(["video/generation_*"], "image/generation_nano_banana_2")
    assert not balancer.matches(["generation_*"], FLUX)
    assert balancer.patterns_of(" Generation_* ,, video/x\n") == ["generation_*", "video/x"]


def test_generation_workflows_go_only_to_the_server_that_claims_them():
    pool = pool_of(ZORO_ROW, GEN_ROW)
    server, _, problem = place(pool, H3_MAX)
    assert server["url"] == GEN and not problem
    server, _, problem = place(pool, FLUX, SAMPLER)   # what no server claims: never the generation server
    assert server["url"] == ZORO and not problem
    pool.take(ZORO, "j1")
    server, alive, problem = place(pool, FLUX, SAMPLER)   # zoro busy: it waits for zoro, the free GEN is not for it
    assert server is None and alive and not problem


def test_a_server_runs_as_many_renders_at_once_as_its_slots():
    pool = pool_of(ZORO_ROW, dict(GEN_ROW, slots=3))
    for n in range(3):
        server, _, _ = place(pool, H3_MAX)
        assert server["url"] == GEN
        pool.take(GEN, "g{}".format(n))
    assert place(pool, H3_MAX) == (None, True, "")   # the fourth waits for a slot
    pool.release(GEN, "g0")
    assert place(pool, H3_MAX)[0]["url"] == GEN
    assert place(pool, FLUX, SAMPLER)[0]["url"] == ZORO
    pool.take(ZORO, "z1")
    assert place(pool, FLUX, SAMPLER) == (None, True, "")   # a ComfyUI server: one at a time
    assert pool.capacity() == 4


def test_the_least_busy_server_that_can_do_it_is_picked_the_first_on_a_tie():
    pool = pool_of(ZORO_ROW, dict(GEN_ROW, slots=4), dict(GEN_ROW, name="Generation 2", url=GEN2, slots=2))
    assert place(pool, H3_MAX)[0]["url"] == GEN   # a tie: the first
    pool.take(GEN, "a")
    assert place(pool, H3_MAX)[0]["url"] == GEN2   # GEN 1/4 busy, GEN2 0/2
    pool.take(GEN2, "b")
    assert place(pool, H3_MAX)[0]["url"] == GEN    # GEN 1/4 against GEN2 1/2


def test_a_render_no_server_could_ever_do_says_why():
    _, _, problem = place(pool_of(GEN_ROW), FLUX, SAMPLER)   # only a server with patterns, which do not take it
    assert "No render server takes " + FLUX in problem
    off = pool_of(ZORO_ROW, dict(GEN_ROW, active=0))
    server, alive, problem = place(off, H3_MAX)
    assert server is None and not alive and "switched off" in problem and "Generation server" in problem
    _, _, problem = place(pool_of(ZORO_ROW, nodes={ZORO: SAMPLER}), H3_MAX, frozenset({"GenerationVideo", "PrimitiveInt"}))
    assert "add the generation server" in problem and "generation_*" in problem   # no generation server added at all


def test_a_server_without_the_nodes_a_workflow_needs_is_not_given_it():
    pool = pool_of(ZORO_ROW, dict(ZORO_ROW, name="Zoro 2", url=ZORO2),
                   nodes={ZORO: {"KSampler"}, ZORO2: {"KSampler", "SaveImage"}})
    assert place(pool, FLUX, SAMPLER)[0]["url"] == ZORO2
    _, _, problem = place(pool, FLUX, frozenset({"KSampler", "WanVideoSampler"}))
    assert "has the nodes" in problem and "WanVideoSampler" in problem and "KSampler" not in problem
    unknown = pool_of(ZORO_ROW, nodes={ZORO: None})   # nodes not known (no /object_info): taken to have them
    assert place(unknown, FLUX, frozenset({"Anything"}))[0]["url"] == ZORO


def test_servers_that_do_not_answer_are_skipped_and_reported_down():
    pool = pool_of(ZORO_ROW, GEN_ROW, dict(GEN_ROW, name="Generation 2", url=GEN2))

    async def only_gen2(url):
        return url == GEN2
    assert place(pool, H3_MAX, answers=only_gen2)[0]["url"] == GEN2

    async def none(url):
        return False
    assert place(pool, H3_MAX, answers=none) == (None, False, "")   # none answers and none runs one: down
    pool.take(GEN, "x")
    assert place(pool, H3_MAX, answers=none) == (None, True, "")    # one runs a render: it is there, only busy


def test_the_generation_server_added_without_its_workflows_still_takes_them():
    """Its Workflows left empty: its nodes (only Generation…) say what it is. The nodes of the workflow's page it never
    runs (PrimitiveInt) must not rule it out, and a render must not wait for a ComfyUI server that is off."""
    pool = pool_of(ZORO_ROW, dict(GEN_ROW, models=""), nodes={ZORO: None, GEN: {"GenerationVideo", "GenerationImage"}})

    async def only_gen(url):   # zoro is off
        return url == GEN
    server, _, problem = place(pool, H3_MAX, frozenset({"GenerationVideo", "PrimitiveInt"}), answers=only_gen)
    assert server["url"] == GEN and not problem
    assert pool.servers()[1]["patterns"] == balancer.GENERATION_ONLY
    assert place(pool, FLUX, SAMPLER)[0]["url"] == ZORO   # a ComfyUI workflow never goes to it
    plain = pool_of(ZORO_ROW, dict(ZORO_ROW, name="Zoro 2", url=ZORO2, models=""), nodes={ZORO2: SAMPLER})
    assert plain.servers()[1]["patterns"] == []   # a ComfyUI server without Workflows takes what no one claims


def test_the_nodes_a_workflow_needs_leave_out_muted_and_page_only_nodes():
    wf = {"nodes": {"1": {"class_type": "KSampler"}, "2": {"class_type": "Note"}, "3": {"class_type": "Upscale"},
                    "4": {"class_type": "Reroute"}},
          "info": {"3": {"mode": 4}, "4": {"virtual": True}}}
    assert balancer.needs_of(wf) == {"KSampler"}


# ---------------------------------------------------------------- the console


def test_the_console_sets_a_servers_workflows_and_jobs_at_once(client):
    register(client)
    desk = console(client)
    desk.post("/api/admin/endpoints", json={"kind": "comfy", "name": "Generation server", "url": "127.0.0.1:8",
                                            "models": "generation_* ,", "slots": 99})
    row = client.app.state.db.one("SELECT * FROM endpoints ORDER BY id DESC LIMIT 1")
    assert (row["models"], row["slots"]) == ("generation_*", endpoints.MOST_SLOTS)   # tidied, kept in range
    desk.put("/api/admin/endpoints/%d" % row["id"], json={"slots": 4})
    shown = next(e for e in desk.get("/api/admin/endpoints?fresh=true").json()["endpoints"] if e["id"] == row["id"])
    assert (shown["models"], shown["slots"]) == ("generation_*", 4)
    pool = client.app.state.comfy_pool
    assert [s["url"] for s in pool.servers()] == ["http://127.0.0.1:9", "http://127.0.0.1:8"]
    assert pool.servers()[1]["patterns"] == ["generation_*"] and pool.capacity() == 5
    pool.take("http://127.0.0.1:8", "j1")
    assert desk.delete("/api/admin/endpoints/%d" % row["id"]).status_code == 400   # a render runs there
    pool.release("http://127.0.0.1:8", "j1")
    assert desk.delete("/api/admin/endpoints/%d" % row["id"]).status_code == 200


# ---------------------------------------------------------------- the queue


class Server(FakeComfy):
    """A fake render server that keeps each render running until told, and takes uploads."""

    def __init__(self, url, entry=None):
        super().__init__(entry=entry)
        self.url = url
        self.uploads = {}

    async def upload(self, filename, data, mime, subfolder=""):
        self.uploads[filename] = data
        self.files[filename] = data
        return filename


@pytest.fixture
def two(client, monkeypatch):
    """The queue over two fake servers: zoro (main, one at a time) and the generation server (generation_*, 2 at once)."""
    register(client)
    manager = client.app.state.jobs
    monkeypatch.setattr(jobs_module, "POLL", 0.05)
    zoro, gen = Server(ZORO), Server(GEN)
    pool = pool_of(ZORO_ROW, dict(GEN_ROW, slots=2))
    pool.clients = {ZORO: zoro, GEN: gen}
    pool.client = lambda url: pool.clients[url]

    async def answers(url):
        return True
    pool.answers = answers
    monkeypatch.setattr(manager, "pool", pool)
    monkeypatch.setattr(manager, "comfy", zoro)
    manager._wake()
    return manager, zoro, gen


def job_on(client, workflow, prompt="A red fox runs.", **extra):
    schema = workflows.describe(workflows.load_workflow(
        client.app.state.catalog.files()[workflow], client.app.state.catalog.saved, workflow))
    role = next(c for c in schema["controls"] if c["role"] == "prompt")
    body = {"workflow": workflow, "values": {role["id"]: prompt}, **extra}
    answer = client.post("/api/jobs", data={"settings": json.dumps(body)})
    assert answer.status_code == 200, answer.text
    return answer.json()["id"]


def status(client, job_id):
    return client.app.state.db.one("SELECT status FROM jobs WHERE id = ?", (job_id,))["status"]


def test_a_waiting_render_does_not_hold_up_the_ones_behind_it(client, two):
    manager, zoro, gen = two
    first = job_on(client, FLUX)
    assert until(lambda: status(client, first) == "running" and zoro.queued)
    second = job_on(client, FLUX)   # waits for zoro
    videos = [job_on(client, H3_MAX) for _ in range(3)]
    assert until(lambda: len(gen.queued) == 2)   # two at once on the generation server, while a FLUX job waits
    assert status(client, second) == "queued" and status(client, videos[2]) == "queued"
    assert all("GenerationVideo" in [n["class_type"] for n in g.values()] for g in gen.queued)
    assert all("GenerationVideo" not in [n["class_type"] for n in g.values()] for g in zoro.queued)
    assert sorted(manager.pool.busy[GEN]) == sorted(videos[:2]) and manager.pool.running(ZORO) == 1


def test_a_render_no_server_can_do_fails_at_once_and_is_refunded(client, two):
    manager, zoro, gen = two
    manager.pool.rows[1]["active"] = 0   # the generation server switched off
    before = credits(client)
    job = job_on(client, H3_MAX)
    row = ended(client, job)
    assert row["status"] == "failed" and "switched off" in row["error"] and credits(client) == before
    assert not gen.queued and not zoro.queued
    assert "switch it on" in errors.for_user(row["error"])


def test_every_graph_says_who_and_where_it_is_from(client, two, tmp_path):
    """extra_data: the user, the project, the module and the job, the same for each clip of a long video."""
    manager, zoro, gen = two
    db = client.app.state.db
    me = client.get("/api/auth/me").json()
    project = db.run("INSERT INTO projects (user_id, name, created) VALUES (?, 'Launch film', ?)", (me["id"], time.time()))
    module = db.run("INSERT INTO projects (user_id, name, parent_id, created) VALUES (?, 'Scene 2', ?, ?)",
                    (me["id"], project, time.time()))
    clip = tmp_path / "generation_00001_.mp4"
    asyncio.run(media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d=1:r=24",
                              "-pix_fmt", "yuv420p", clip))
    gen.files[clip.name] = clip.read_bytes()
    gen.entry = {"status": {"status_str": "success", "completed": True},
                 "outputs": {"10": {"videos": [{"filename": clip.name, "subfolder": "video", "type": "output"}]}}}
    job = job_on(client, H3_MAX, "A fox runs.\n---\nThe fox stops.", clips=2, project_id=module)
    assert ended(client, job)["status"] == "done"
    assert len(gen.extras) == 2 and gen.extras[0] == gen.extras[1]
    scene = gen.extras[0]["scene"]
    assert scene["user"] == {"id": me["id"], "name": me["name"], "email": me["email"]}
    assert (scene["project"]["id"], scene["project"]["name"]) == (project, "Launch film")
    assert (scene["module"]["id"], scene["module"]["name"]) == (module, "Scene 2")
    assert scene["job"]["id"] == job
    on_canvas = manager._who({"id": "j", "name": "x", "user_id": me["id"], "project_id": project})["scene"]
    assert on_canvas["module"]["name"] == "Main canvas" and on_canvas["project"]["id"] == project
    alone = manager._who({"id": "j", "name": "x", "user_id": me["id"], "project_id": None})["scene"]
    assert "project" not in alone and "module" not in alone


def test_a_provider_error_reads_as_the_provider_wrote_it(client, two):
    manager, zoro, gen = two
    reason = "Test mode: The provider would charge 30 credits for this job."
    gen.entry = {"status": {"status_str": "error", "completed": False, "messages": [
        ["execution_error", {"node_type": "The provider", "exception_message": reason}]]}}
    row = ended(client, job_on(client, H3_MAX))
    assert row["status"] == "failed" and row["error"] == "The provider: " + reason
    assert errors.for_user(row["error"]) == "The provider: " + reason
    assert jobs_module._execution_error({"messages": [["execution_error", {"node_type": "KSampler", "exception_message": "x"}]]}) \
        == "ComfyUI error in node 'KSampler': x"


def test_a_cancelled_provider_job_says_the_provider_still_charges(client, two):
    manager, zoro, gen = two
    before = credits(client)
    job = job_on(client, H3_MAX)
    assert until(lambda: gen.queued)
    assert client.delete("/api/jobs/" + job).status_code == 200
    row = ended(client, job)
    assert row["status"] == "cancelled" and "no cancel" in row["error"] and credits(client) == before


class Off(Server):
    """A render server that is switched off: nothing it is asked answers."""

    async def view(self, filename, subfolder="", kind="output"):
        raise httpx.ConnectTimeout("off")

    async def upload(self, filename, data, mime, subfolder=""):
        raise httpx.ConnectTimeout("off")


def test_a_job_with_references_is_added_and_run_while_the_main_server_is_off(client, two, monkeypatch):
    """The references are kept by the studio when the job is added, and sent to the server that runs it when it starts:
    the main server (the first in the console) is never asked, so it being off stops nothing."""
    manager, zoro, gen = two
    off = Off(ZORO)
    monkeypatch.setattr(manager, "comfy", off)
    manager.pool.clients[ZORO] = off
    store = client.app.state.storage
    name = asyncio.run(keep_reference(store, "face.png", b"face picture"))
    settings = {"refs": {"201:image": {"comfy_name": name, "name": "face"}, "202:image": {"comfy_name": name}}}
    asyncio.run(manager._send_inputs(settings, gen))
    assert gen.uploads == {name: b"face picture"}   # from the studio's copy, once
    gen.uploads.clear()
    asyncio.run(manager._send_inputs(settings, gen))
    assert gen.uploads == {}   # it has it already: not sent again
    zoro_up = Server(ZORO)
    monkeypatch.setattr(manager, "comfy", zoro_up)
    asyncio.run(manager._send_inputs(settings, zoro_up))   # the main server gets them the same way
    assert zoro_up.uploads == {name: b"face picture"}


def test_a_reference_from_before_the_studio_kept_them_comes_from_the_main_server(client, two, monkeypatch):
    manager, zoro, gen = two
    old = "scene_0123456789_old.png"   # put on the main server only, by an older studio
    zoro.files[old] = b"old picture"
    asyncio.run(manager._send_inputs({"refs": {"a": {"comfy_name": old}}}, gen))
    assert gen.uploads == {old: b"old picture"}
    monkeypatch.setattr(manager, "comfy", Off(ZORO))
    with pytest.raises(ComfyError, match="does not answer"):
        asyncio.run(manager._send_inputs({"refs": {"a": {"comfy_name": "scene_9999999999_gone.png"}}}, gen))


# ---------------------------------------------------------------- jobs at once, and what the provider refuses

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
REFUSAL = ("bad_resolution_with_references — MiniMax H3 Max with reference images or audio renders at 1080p, "
           "768p only.")


def test_ten_jobs_at_once_means_ten_renders_side_by_side(client, two):
    manager, zoro, gen = two
    manager.pool.rows[1]["slots"] = 10
    client.app.state.db.run("UPDATE users SET credits = 100000")
    made = [job_on(client, H3_MAX) for _ in range(12)]
    assert until(lambda: len(gen.queued) == 10)
    time.sleep(0.3)   # and no more than ten
    assert len(gen.queued) == 10 and sorted(status(client, j) for j in made).count("queued") == 2
    assert manager.pool.running(GEN) == 10


def video_with_reference(client, resolution="480p"):
    schema = workflows.describe(workflows.load_workflow(
        client.app.state.catalog.files()[H3_MAX], client.app.state.catalog.saved, H3_MAX))
    option = generation_models.option_for(schema, "resolution", "minimax_h3_max")
    body = {"workflow": H3_MAX, "values": {"1:value": "The baron raises a glass."},
            "options": {"model": "minimax_h3_max", option["id"]: resolution}}
    answer = client.post("/api/jobs", data={"settings": json.dumps(body)}, files={"ref:ref_1": ("baron.png", PNG, "image/png")})
    assert answer.status_code == 200, answer.text
    return answer.json()["id"], option["id"]


def test_minimax_h3_max_with_references_is_made_at_768p_not_480p(client, two):
    manager, zoro, gen = two
    job, option = video_with_reference(client)
    settings = json.loads(client.app.state.db.one("SELECT settings FROM jobs WHERE id = ?", (job,))["settings"])
    assert settings["options"][option] == "768p" and "768p" in settings["resolution_note"]
    # without references it stays at 480p
    plain = job_on(client, H3_MAX)
    assert json.loads(client.app.state.db.one("SELECT settings FROM jobs WHERE id = ?", (plain,))["settings"]).get("options", {}).get(option, "480p") == "480p"


class RefusesFirst(Server):
    """The generation server, whose provider refuses the first job as MiniMax H3 Max's 480p with references was."""

    async def history(self, prompt_id):
        if prompt_id == "p1":
            return {"status": {"status_str": "error", "completed": False, "messages": [
                ["execution_error", {"node_type": "The provider", "exception_message": REFUSAL}]]}}
        return None


def test_a_refusal_that_names_the_resolutions_is_learned_and_the_job_made_again(client, two, monkeypatch):
    manager, zoro, gen = two
    monkeypatch.setattr(generation_models, "WITH_REFERENCES", {})   # not known yet: learned from the provider
    refusing = RefusesFirst(GEN)
    manager.pool.clients[GEN] = refusing
    job, option = video_with_reference(client)
    assert until(lambda: len(refusing.queued) == 2)   # refused, then queued again by itself
    first, second = (json.dumps(g) for g in refusing.queued)
    assert '"480p"' in first and '"768p"' in second and '"480p"' not in second
    row = client.app.state.db.one("SELECT status, error, settings FROM jobs WHERE id = ?", (job,))
    assert row["status"] in ("running", "queued") and not row["error"] and json.loads(row["settings"])["refitted"]
    assert generation_models.reference_rules(client.app.state.db)["minimax_h3_max"] == ["768p", "1080p"]
    # the next one is fitted before it is sent
    _, _ = video_with_reference(client)
    assert until(lambda: len(refusing.queued) == 3) and '"768p"' in json.dumps(refusing.queued[2])


class Rejects(Server):
    """The generation server refusing a job against its model's rules, before the provider is asked."""

    async def queue(self, prompt, client_id, extra=None):
        raise ComfyError("ComfyUI rejected the workflow. MiniMax H3 Max can't combine first/last frames with reference "
                         "images or audio (only Seedance can).")


def test_the_generation_servers_refusal_reads_as_it_wrote_it(client, two):
    manager, zoro, gen = two
    manager.pool.clients[GEN] = Rejects(GEN)
    row = ended(client, job_on(client, H3_MAX))
    assert row["status"] == "failed" and row["error"].startswith("The generation server: MiniMax H3 Max can't combine")
    assert errors.for_user(row["error"]) == row["error"]   # not "something went wrong on the render server"


class NotReadyFirst(Server):
    """The provider, not ready the first time: the references just sent are still being registered."""

    async def history(self, prompt_id):
        if prompt_id == "p1":
            return {"status": {"status_str": "error", "completed": False, "messages": [
                ["execution_error", {"node_type": "The provider",
                                     "exception_message": "The provider did not start the clip: references_registering"}]]}}
        return None


def test_a_job_the_provider_was_not_ready_for_is_made_again_a_moment_later(client, two, monkeypatch):
    manager, zoro, gen = two
    monkeypatch.setattr(jobs_module, "NOT_READY_WAIT", 0.1)
    waiting = NotReadyFirst(GEN)
    manager.pool.clients[GEN] = waiting
    before = credits(client)
    job = job_on(client, H3_MAX)
    assert until(lambda: len(waiting.queued) == 2)   # refused as not ready, then sent again by itself
    row = client.app.state.db.one("SELECT status, error, settings FROM jobs WHERE id = ?", (job,))
    assert row["status"] in ("running", "queued") and not row["error"]
    assert json.loads(row["settings"])["not_ready_tries"] == 1 and credits(client) < before   # still held, not refunded


def test_a_provider_that_is_never_ready_fails_the_job_after_a_few_tries(client, two, monkeypatch):
    manager, zoro, gen = two
    monkeypatch.setattr(jobs_module, "NOT_READY_WAIT", 0.05)
    gen.entry = {"status": {"status_str": "error", "completed": False, "messages": [
        ["execution_error", {"node_type": "The provider", "exception_message": "The provider did not start the clip: references_registering"}]]}}
    row = ended(client, job_on(client, H3_MAX))
    assert row["status"] == "failed" and "references_registering" in row["error"] and len(gen.queued) == 1 + jobs_module.NOT_READY_TRIES


class NeverWithAFrame(Server):
    """The provider, which never starts Seedance with a first frame and references: "references_registering"."""

    async def history(self, prompt_id):
        graph = self.queued[int(prompt_id[1:]) - 1]
        if any(n["class_type"] == "GenerationOptionalImage" and "first" in n.get("_meta", {}).get("title", "").lower()
               and n["inputs"].get("image") not in (None, "", "none") for n in graph.values()):
            return {"status": {"status_str": "error", "completed": False, "messages": [
                ["execution_error", {"node_type": "The provider",
                                     "exception_message": "The provider did not start the clip: references_registering"}]]}}
        return None


def test_a_clip_never_started_with_its_frame_is_made_from_its_references_only(client, two, monkeypatch):
    manager, zoro, gen = two
    monkeypatch.setattr(jobs_module, "NOT_READY_WAIT", 0.05)
    refusing = NeverWithAFrame(GEN)
    manager.pool.clients[GEN] = refusing
    first = workflows.describe(workflows.load_workflow(
        client.app.state.catalog.files()[H3_MAX], client.app.state.catalog.saved, H3_MAX))["slots"]["first_frame"]
    body = {"workflow": H3_MAX, "values": {"1:value": "Claire climbs out of the car."}, "options": {"model": "seedance_2_5"}}
    answer = client.post("/api/jobs", data={"settings": json.dumps(body)},
                         files={"ref:" + first: ("crash_last.png", PNG, "image/png"), "ref:ref_1": ("claire.png", PNG, "image/png")})
    assert answer.status_code == 200, answer.text
    job = answer.json()["id"]
    assert until(lambda: len(refusing.queued) == 3)   # as it was, again after a moment, then from its references only
    settings = json.loads(client.app.state.db.one("SELECT settings FROM jobs WHERE id = ?", (job,))["settings"])
    assert settings["frames_dropped"] == [first] and first not in settings["refs"] and "ref_1" in settings["refs"]
    assert status(client, job) in ("running", "queued")
