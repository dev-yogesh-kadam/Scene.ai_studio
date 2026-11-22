"""On this PC: the studio's own tools as a provider (providers/local.py, migration 0018) and the script they run in
(backend/local_tools/run.py). The adapter is tried with a fake script, so no GPU, PyTorch or model is needed."""

import asyncio
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from scene import agent
from scene.providers import local, registry, v1 as provider_v1, workflows as provider_workflows
from scene.providers.base import ProviderProblem, RequestProblem
from scene.providers.local import LocalTools

RUN = Path(__file__).resolve().parents[1] / "local_tools" / "run.py"

# A stand-in for run.py: "check" says both tools are ready; a tool writes its outputs, or fails on a file named "bad".
FAKE = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    if sys.argv[1] == "check":
        print(json.dumps({"device": "cpu", "transcribe": {"ready": True, "why": ""}, "separate_voice": {"ready": True, "why": ""}}))
        sys.exit(0)
    folder = Path(sys.argv[2])
    job = json.loads((folder / "job.json").read_text())
    source = job["input"].get("audio") or job["input"].get("video")
    print(json.dumps({"progress": 0.5, "message": "Half way"}), flush=True)
    time.sleep(1.3)   # long enough for a look while it works (local.POLL)
    if Path(source).read_bytes() == b"bad":
        print(json.dumps({"error": "The file has no sound."}))
        sys.exit(1)
    if Path(source).read_bytes() == b"slow":
        time.sleep(30)
    if sys.argv[1] == "transcribe":
        (folder / "transcript.json").write_text(json.dumps({"language": job["input"].get("language"), "segments": [], "words": []}))
        (folder / "transcript.srt").write_text("")
        print(json.dumps({"done": True, "outputs": [{"name": "transcript.json", "mime": "application/json"},
                                                     {"name": "transcript.srt", "mime": "application/x-subrip"}]}))
    else:
        (folder / "voice.wav").write_bytes(b"voice")
        (folder / "music_fx.wav").write_bytes(b"music")
        print(json.dumps({"done": True, "outputs": [{"name": "voice.wav"}, {"name": "music_fx.wav"}]}))
''')


@pytest.fixture
def tools(tmp_path, monkeypatch):
    script = tmp_path / "fake_run.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setattr(local, "SCRIPT", script)
    local._checked.clear()
    local.JOBS.clear()
    return LocalTools(python=sys.executable, work_dir=str(tmp_path / "work"), models_dir=str(tmp_path / "models"))


def run(coroutine):
    return asyncio.run(coroutine)


def test_with_no_python_nothing_is_offered_and_nothing_is_said(tmp_path):
    """Its Python not there (a server, Zoro) or switched off: no model, no alert, and a job is sent elsewhere."""
    local._checked.clear()
    for tools in (LocalTools(python=str(tmp_path / "missing" / "python.exe"), work_dir=str(tmp_path / "work")),
                  LocalTools(python=sys.executable, work_dir=str(tmp_path / "work"), switch="off")):
        assert not tools.present and run(tools.models("")) == []
        said = run(tools.whoami(""))
        assert said["key"]["max_concurrent"] == 1 and said["key"]["mode"] == "live" and said["alerts"] == []
        with pytest.raises(ProviderProblem):   # a ProviderProblem: the router tries the next provider
            run(tools.start("", "transcribe", {"audio": "local:x"}, {}, "scene-job-1"))


def test_with_its_python_there_a_tool_not_installed_still_says_why(tmp_path, monkeypatch):
    script = tmp_path / "check.py"
    script.write_text('import json; print(json.dumps({"device": "cpu", "transcribe": {"ready": False, "why": "Install '
                      'faster-whisper."}, "separate_voice": {"ready": True, "why": ""}}))', encoding="utf-8")
    monkeypatch.setattr(local, "SCRIPT", script)
    local._checked.clear()
    tools = LocalTools(python=sys.executable, work_dir=str(tmp_path / "work"))
    assert tools.present and run(tools.whoami(""))["alerts"] == ["Install faster-whisper."]
    assert {m["id"] for m in run(tools.models(""))} == {"separate_voice"}


def test_the_ready_tools_are_offered_free_each_with_one_required_file(tools):
    found = {m["id"]: m for m in run(tools.models(""))}
    assert set(found) == {"transcribe", "transcribe_video", "separate_voice"}
    assert found["transcribe_video"]["capability"] == "transcribe"
    assert all(m["pricing"] == {"unit": "job", "credits": 0} for m in found.values())
    assert found["transcribe"]["input_schema"]["required"] == ["audio"]
    assert found["transcribe_video"]["input_schema"]["required"] == ["video"]
    assert provider_v1.file_fields(found["separate_voice"]["input_schema"]) == {"audio": ("audio", False, 1)}


def test_a_job_runs_follows_and_hands_back_its_files_free(tools, tmp_path):
    async def go():
        sent = await tools.upload("", name="vo.mp3", data=b"sound")
        started = await tools.start("", "transcribe", {"audio": sent, "language": "hi"}, {}, "scene-job-7")
        assert started["quote"] == {"credits": 0, "source": "local"}
        seen = []
        answer = await tools.follow("", started["id"], seen.append)
        assert answer["status"] == "succeeded" and answer["cost"] == 0
        assert [o["name"] for o in answer["outputs"]] == ["transcript.json", "transcript.srt"]
        assert any(a.get("message") == "Half way" for a in seen)
        target = tmp_path / "out" / "t.json"
        await tools.fetch_output("", started["id"], 0, target)
        assert json.loads(target.read_text())["language"] == "hi"
        again = await tools.start("", "transcribe", {"audio": sent}, {}, "scene-job-7")   # a retry runs nothing twice
        assert again["id"] == started["id"] and again.get("replayed")
    run(go())


def test_a_failed_tool_says_why_in_words(tools):
    async def go():
        sent = await tools.upload("", name="x.wav", data=b"bad")
        started = await tools.start("", "separate_voice", {"audio": sent}, {}, "scene-job-8")
        answer = await tools.follow("", started["id"])
        assert answer["status"] == "failed"
        problem = provider_v1.job_problem(answer)
        assert "no sound" in str(problem)
    run(go())


def test_a_job_needs_its_file_and_only_one_sent_to_this_pc(tools, tmp_path):
    async def go():
        with pytest.raises(RequestProblem, match="audio file"):
            await tools.start("", "transcribe", {"language": "en"}, {}, "a")
        with pytest.raises(RequestProblem, match="video"):
            await tools.start("", "transcribe_video", {"audio": await tools.upload("", name="a.wav", data=b"x")}, {}, "b")
        outside = tmp_path / "elsewhere.wav"
        outside.write_bytes(b"x")
        with pytest.raises(RequestProblem):   # a path that was never sent here is refused
            await tools.start("", "transcribe", {"audio": "local:" + str(outside)}, {}, "c")
        with pytest.raises(RequestProblem):
            await tools.start("", "upscale_video", {}, {}, "d")
    run(go())


def test_a_cancelled_job_stops_and_costs_nothing(tools):
    async def go():
        sent = await tools.upload("", name="slow.wav", data=b"slow")
        started = await tools.start("", "separate_voice", {"audio": sent}, {}, "scene-job-9")
        stop = []
        asyncio.get_running_loop().call_later(1.5, stop.append, True)
        answer = await tools.follow("", started["id"], cancelled=lambda: bool(stop))
        assert answer["status"] == "cancelled" and answer["charged"] is False
    run(go())


def test_run_now_gives_the_files_by_name(tools, tmp_path):
    source = tmp_path / "track.wav"
    source.write_bytes(b"sound")
    made = run(tools.run_now("separate_voice", {"audio": str(source)}))
    assert Path(made["voice.wav"]).read_bytes() == b"voice"
    assert Path(made["music_fx.wav"]).read_bytes() == b"music"


def test_a_job_lost_in_a_restart_fails_saying_so(tools):
    answer = run(tools.status("", "local_gone"))
    assert answer["status"] == "failed" and "restarted" in answer["error"]["message"]


# ---------------------------------------------------------------- the registry, the catalog and the agent

def test_on_this_pc_is_made_once_with_one_key_and_cannot_be_added_keyed_or_removed(database):
    registry.seed(database, None)
    registry.seed(database, None)
    rows = [p for p in registry.providers(database) if p["kind"] == "local_tools"]
    assert len(rows) == 1 and rows[0]["name"] == "On this PC"
    own = registry.keys(database, rows[0]["id"])
    assert len(own) == 1 and own[0]["label"] == "This PC" and own[0]["max_concurrent"] == 1
    with pytest.raises(ValueError):
        registry.add_provider(database, "local_tools")
    with pytest.raises(ValueError):
        registry.add_key(database, rows[0]["id"], "anything")
    with pytest.raises(ValueError):
        registry.remove_provider(database, rows[0]["id"])


def test_its_models_are_offered_as_sound_workflows_the_agent_knows(database, tools):
    registry.seed(database, None)
    row = next(p for p in registry.providers(database) if p["kind"] == "local_tools")
    key = registry.keys(database, row["id"])[0]
    registry.save_models(database, row["id"], key["id"], run(tools.models("")))
    found = provider_workflows.ProviderWorkflows(database)._read()
    assert {"audio/@transcribe", "audio/@transcribe_video", "audio/@separate_voice"} <= set(found)
    offers = registry.provider_offers(database)
    assert {m["id"] for m in offers["transcribe"]} == {"transcribe", "transcribe_video"}
    wf = found["audio/@transcribe"]
    assert wf["profile"]["required_refs"] and wf["profile"]["provider"]["pricing"]["credits"] == 0
    offer = {"id": "audio/@transcribe", "references": [{"required": True, "takes": "audio"}]}
    assert agent.takes_sound([offer]) == {"audio/@transcribe"}


# ---------------------------------------------------------------- run.py itself (the studio's Python has no PyTorch)

def test_the_script_says_what_is_missing_in_words():
    out = subprocess.run([sys.executable, str(RUN), "check"], capture_output=True, text=True, timeout=120)
    said = json.loads(out.stdout.strip().splitlines()[-1])
    assert set(said) >= {"device", "transcribe", "separate_voice"}
    for tool in ("transcribe", "separate_voice"):
        assert said[tool]["ready"] or "pip install" in said[tool]["why"]


def test_the_script_writes_subtitle_times_as_srt_wants_them():
    sys.path.insert(0, str(RUN.parent))
    try:
        import run as script
    finally:
        sys.path.remove(str(RUN.parent))
    assert script._srt_time(0) == "00:00:00,000"
    assert script._srt_time(3661.5) == "01:01:01,500"
    assert script._r(1.23456) == 1.235


# ---------------------------------------------------------------- On this PC beside a Scene provider (Zoro, LUFI)

def settings_for(tmp_path, python, switch="auto"):
    from scene.config import Settings
    return Settings(storage_dir=str(tmp_path / "storage"), local_tools_python=str(python), local_tools=switch)


def test_on_this_pc_is_offered_only_where_its_python_is_and_not_switched_off(tmp_path):
    assert local.offered(sys.executable) and local.offered(sys.executable, "auto")
    assert not local.offered(sys.executable, "off") and not local.offered(sys.executable, "OFF")
    assert not local.offered(str(tmp_path / "none.exe")) and not local.offered("")
    assert local.offered_by(settings_for(tmp_path, sys.executable))
    assert not local.offered_by(settings_for(tmp_path, sys.executable, "off"))
    assert not local.offered_by(settings_for(tmp_path, tmp_path / "none.exe"))


def both_offer(database, model="transcribe"):
    """On this PC and a Scene provider (Studio_automation) both offering `model`, each with its one key."""
    registry.seed(database, None)
    here = next(p for p in registry.providers(database) if p["kind"] == "local_tools")
    here_key = registry.keys(database, here["id"])[0]["id"]
    registry.save_models(database, here["id"], here_key, [{"id": model, "name": "Transcribe", "capability": "transcribe"}])
    there = registry.add_provider(database, "scene_provider_v1", "Studio automation", "http://studio-automation:8189", 5)
    there_key = registry.add_key(database, there, "sa_live_sound0001", "LUFI")
    registry.save_models(database, there, there_key, [{"id": model, "name": "Transcribe", "capability": "transcribe"}])
    return here_key, there_key


def test_the_router_prefers_the_provider_that_is_ready(database, tmp_path, monkeypatch):
    from scene.providers.router import Router
    here_key, there_key = both_offer(database)
    router = Router(database, settings_for(tmp_path, sys.executable))
    python = str(router.settings.path("local_tools_python"))
    database.run("UPDATE provider_keys SET status = 'ok' WHERE id IN (?, ?)", (here_key, there_key))
    # On this PC's tool found not installed at the last look: Studio_automation runs it, though On this PC comes first
    monkeypatch.setitem(local._checked, python, (time.time(), {"transcribe": {"ready": False, "why": "x"}}))
    assert router.pick("transcribe")[0]["key"]["id"] == there_key
    # installed: On this PC (first by priority) is ready too
    monkeypatch.setitem(local._checked, python, (time.time(), {"transcribe": {"ready": True, "why": ""}}))
    router.forget()
    assert router.pick("transcribe")[0]["key"]["id"] == here_key
    # Studio_automation's key not found well at its last check (status unknown): On this PC, which is ready
    database.run("UPDATE provider_keys SET status = 'unknown' WHERE id = ?", (there_key,))
    router.forget()
    assert router.pick("transcribe")[0]["key"]["id"] == here_key


def test_where_on_this_pc_is_not_offered_it_is_never_routed_listed_or_kept(database, tmp_path):
    from scene.providers.router import Router
    here_key, there_key = both_offer(database)
    database.run("UPDATE provider_keys SET status = 'ok' WHERE id IN (?, ?)", (here_key, there_key))
    for settings in (settings_for(tmp_path, tmp_path / "no-python" / "python"), settings_for(tmp_path, sys.executable, "off")):
        router = Router(database, settings)
        assert [c["key"]["id"] for c in router.candidates("transcribe")] == [there_key]
        assert router.pick("transcribe")[0]["key"]["id"] == there_key
        assert "local_tools" not in [p["kind"] for p in registry.listing(database, settings)]   # never a broken provider
    # with its Python there, it is listed and routed again
    shown = settings_for(tmp_path, sys.executable)
    assert "local_tools" in [p["kind"] for p in registry.listing(database, shown)]
    assert len(Router(database, shown).candidates("transcribe")) == 2
    # at start where it is not offered, its models cached elsewhere (a database copied from LUFI) and its alerts go
    registry.mark(database, here_key, error="The tools' Python is not there", info={"alerts": ["The tools' Python is not there"]})
    registry.seed(database, settings_for(tmp_path, sys.executable, "off"))
    assert registry.models(database, key_id=here_key) == [] and registry.models(database, key_id=there_key)
    row = registry.key(database, here_key)
    assert row["last_error"] == "" and registry.shown_key(row)["alerts"] == []


def test_checking_on_this_pc_where_it_is_not_offered_says_nothing(database, tmp_path):
    from scene.providers.router import Router
    registry.seed(database, None)
    here = next(p for p in registry.providers(database) if p["kind"] == "local_tools")
    key_row = registry.keys(database, here["id"])[0]
    router = Router(database, settings_for(tmp_path, sys.executable, "off"))
    said = run(router.check_key(here, key_row))
    assert said["ok"] and said["models"] == 0 and said["alerts"] == []
