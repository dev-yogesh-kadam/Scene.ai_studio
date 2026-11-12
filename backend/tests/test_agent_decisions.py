"""The agent decides a shot's length, shape, resolution and the workflow's own settings; the server keeps what is allowed."""

from test_api import register

SHOT = {"tool": "generate", "workflow": "video/h3_all_in_one", "uses": [], "clips": 1, "start_from": 0, "after": 0}


def plan(client, monkeypatch, *steps, instruction="an ad for Reels"):
    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        plan.asked = message
        return {"reply": "Planned.", "steps": list(steps)}
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    return client.post("/api/agent/plan", json={"instruction": instruction}).json()["steps"]


MUSIC = {"tool": "generate", "workflow": "audio/audio_minimax_music_3", "name": "Music", "prompt": "Upbeat pop.", "uses": [], "clips": 1,
         "start_from": 0, "after": 0, "duration": 300, "choices": [{"setting": "37:13:max_duration", "value": "300"}]}


def test_music_lasts_what_was_asked_or_what_the_shots_add_up_to_not_what_the_model_wants(client, monkeypatch):
    register(client)
    # The model asks for the longest song; the user named 25 seconds, so it is 30, the shortest length that covers it.
    song = plan(client, monkeypatch, MUSIC, instruction="Make upbeat music for a 25 second ad.")[0]
    assert song["settings"]["values"]["37:13:max_duration"] == 30 and song["credits"] == 150    # 30 s at 5 cr a second
    # Music for the shots of the same plan: 7 + 8 seconds of video, so 30 seconds of music.
    steps = plan(client, monkeypatch, dict(SHOT, name="One", prompt="A pour.", duration=7), dict(SHOT, name="Two", prompt="A smile.", duration=8),
                 MUSIC, instruction="two shots and music for them")
    assert steps[2]["settings"]["values"]["37:13:max_duration"] == 30
    # Nothing to go by: the model's choice stands.
    assert plan(client, monkeypatch, MUSIC, instruction="a long ambient piece")[0]["settings"]["values"]["37:13:max_duration"] == 300


def test_the_agent_sets_length_shape_resolution_and_the_workflows_own_settings(client, monkeypatch):
    register(client)
    step = plan(client, monkeypatch, dict(SHOT, name="Pour", prompt="Coffee pours into a cup.", duration=7, orientation="portrait",
                                          resolution=480, why="7 s for the pour; portrait for Reels; a draft",
                                          choices=[{"setting": "quality", "value": "high"}, {"setting": "sound", "value": "off"},
                                                   {"setting": "engine", "value": "first_frame"}, {"setting": "quality", "value": "ultra"},
                                                   {"setting": "made_up", "value": "x"}, "junk"]))[0]
    settings = step["settings"]
    assert settings["values"]["102:value"] == 7 and settings["options"]["shape"] == "portrait" and settings["values"]["501:value"] == 480
    # "ultra" and the made-up setting are ignored, and first-frame mode needs a picture to start on, which this shot has not
    assert settings["options"] == {"engine": "reference", "quality": "high", "shape": "portrait", "sound": "off", "keyframes": "off", "upscale": "off",
                                   "sharpen": "off", "best_upscale": "7b", "smooth": "off"}
    assert step["why"] == "7 s for the pour; portrait for Reels; a draft"
    assert "7 s" in step["facts"]
    # What the model was told: the length it may choose and the settings it may set, with what each value means.
    assert '"duration_seconds": "4 to 15' in plan.asked and '"setting": "quality"' in plan.asked and '"setting": "shape"' in plan.asked


def test_a_shot_is_long_enough_for_its_dialogue_and_stays_within_4_to_15_seconds(client, monkeypatch):
    register(client)
    words = "Every morning I open this shop before the town wakes up, and the first cup is always mine to enjoy"   # 20 words
    steps = plan(client, monkeypatch,
                 dict(SHOT, name="Talk", prompt='She smiles. Audio: "{}"'.format(words), duration=4),
                 dict(SHOT, name="Blink", prompt="A quick glance.", duration=2),
                 dict(SHOT, name="Epic", prompt="A long crane move.", duration=99, resolution=1080),
                 dict(SHOT, name="Hero", prompt="The cup on the counter.", duration=8, resolution=1080))
    lengths = {s["name"]: s["settings"]["values"]["102:value"] for s in steps}
    assert lengths == {"Talk": 10, "Blink": 4, "Epic": 15, "Hero": 8}   # 20 words need 10 s; 2 s is raised to 4; 99 is cut to 15
    sizes = {s["name"]: s["settings"]["values"]["501:value"] for s in steps}
    assert sizes["Epic"] == 720 and sizes["Hero"] == 1080    # a shot over 10 s is not made larger than the workflow's own size


def test_the_settings_offered_include_choice_lists_and_unknown_values_are_ignored():
    from scene import agent
    schema = {"options": [{"id": "quality", "label": "Quality", "default": "medium",
                           "choices": [{"id": "low", "label": "Low", "hint": "a draft"}, {"id": "high", "label": "High"}]}],
              "controls": [{"id": "37:13:max_duration", "role": None, "label": "Length in seconds", "default": 60, "choices": [30, 60, 120]},
                           {"id": "1:text", "role": "prompt", "label": "Prompt", "default": "", "choices": None}]}
    offered = agent.choosable_settings(schema)
    assert [s["setting"] for s in offered] == ["quality", "37:13:max_duration"]
    assert offered[0]["choices"][0] == {"value": "low", "means": "a draft"} and offered[1]["choices"][2] == {"value": "120"}
    settings = {"options": {"quality": "medium"}, "values": {"37:13:max_duration": 60}}
    agent.apply_choices(schema, settings, [{"setting": "37:13:max_duration", "value": "120"}, {"setting": "37:13:max_duration", "value": "45"},
                                           {"setting": "quality", "value": "low"}, {"setting": "1:text", "value": "sneaky"}])
    assert settings == {"options": {"quality": "low"}, "values": {"37:13:max_duration": 120}}   # a number stays a number
    # A setting named by its label is found too, but an id always wins over a label ("mode" is the speed, not the Mode).
    both = dict(schema, options=[{"id": "mode", "label": "Speed", "choices": [{"id": "fast"}, {"id": "normal"}]},
                                 {"id": "engine", "label": "Mode", "choices": [{"id": "reference"}, {"id": "first_frame"}]}])
    named = {"options": {"mode": "fast", "engine": "reference"}, "values": {}}
    agent.apply_choices(both, named, [{"setting": "Speed", "value": "normal"}, {"setting": "mode", "value": "first_frame"}])
    assert named["options"] == {"mode": "normal", "engine": "reference"}
    assert agent.spoken_seconds('Audio: "Hello there."') == 3 and agent.spoken_seconds("No one speaks.") == 0
    assert agent.spoken_seconds("She says: 'This is the best latte in town, I come here every morning before work'.") == 8
    assert agent.spoken_seconds("The dog's bowl is empty and it doesn't care.") == 0      # apostrophes, not quotes


def test_a_reply_that_says_it_is_making_something_without_a_plan_is_caught():
    from scene import agent
    assert agent.claims_work("generate", "Generating the 480p clip now.")
    assert agent.claims_work("approve", "I have generated the low-quality clip.")
    assert not agent.claims_work("what did you generate last time?", "I generated a car clip.")   # a question is answered in words
    assert not agent.claims_work("hi", "Hello. What are we making?")
    # the history tells the model that such a reply made nothing; a plain answer is left as it was
    turns = agent.past_turns([{"instruction": "start", "reply": "Generating it now.", "steps": []},
                              {"instruction": "hi", "reply": "Hello.", "steps": []}])
    assert turns[1]["content"].endswith("(No plan with this reply: nothing was made or queued.)")
    assert turns[3]["content"] == "Hello."


def test_a_bare_go_ahead_after_a_reply_without_a_plan_carries_that_reply():
    from scene import agent
    history = [{"instruction": "a pet ad", "reply": "A puppy runs across a lawn chasing a red ball.", "steps": []}]
    for said in ("start", "approve", "generate", "go ahead", "generate your own", "from scratch"):
        assert "A puppy runs across a lawn" in agent.carry_over(said, history), said
    assert agent.carry_over("make the dog brown and add rain to the whole scene please", history).startswith("make the dog")
    assert agent.carry_over("start", [dict(history[0], steps=["Puppy"])]) == "start"   # after a plan, Approve is the button


def test_an_empty_section_of_the_prompt_structure_is_left_out():
    from scene import agent
    assert agent.EMPTY_SECTION.match("REFERENCES:") and agent.EMPTY_SECTION.match("LIGHT AND LOOK: none")
    assert not agent.EMPTY_SECTION.match("SCENE CONTEXT: a fox in a den.") and not agent.EMPTY_SECTION.match("She says: ")


# ---------------------------------------------------------------- the checks in any language (the model says them)

def test_the_checks_take_the_models_word_and_fall_back_to_english_without_it():
    from scene import agent
    # with the field, the model's word stands, in any language
    assert agent.claims_work("इसे बना दो", "मैं इसे अभी बना रहा हूँ।", True)
    assert not agent.claims_work("generate", "Generating the clip now.", False)
    assert agent.wants_sound("ponle esta música al vídeo", (), True) and not agent.wants_sound("add music to the video", (), False)
    assert agent.parts_asked("divídelo en tres", {"tool": "trim", "parts": 3}) == 3
    assert agent.parts_asked("divídelo en tres", {"tool": "trim", "parts": 9}) == 0   # out of 2 to 6: not trusted
    # without it, the English words, as before
    assert agent.claims_work("generate", "Generating the clip now.") and not agent.claims_work("इसे बना दो", "मैं इसे बना रहा हूँ।")
    assert agent.wants_sound("add the music to this video") and agent.parts_asked("split it in two", {"parts": 1}) == 2
    # the model is made to decide each: they are required in its answer
    assert {"claims_making", "wants_sound", "go_ahead"} <= set(agent.reply_format(["w"])["required"])
    shaped = agent.shaped({"reply": "x", "claims_making": True, "wants_sound": "yes"})
    assert shaped["claims_making"] is True and shaped["wants_sound"] is None and shaped["go_ahead"] is None


def test_a_go_ahead_in_any_language_carries_the_last_reply_and_the_model_decides(client, monkeypatch):
    from scene import agent
    register(client)
    history = [{"instruction": "a pet ad", "reply": "A puppy runs across a lawn chasing a red ball.", "steps": []}]
    for said in ("इसे बना दो", "hazlo"):   # "make it", "do it": no English word the old check knew
        assert "A puppy runs across a lawn" in agent.carry_over(said, history) and "go_ahead" in agent.carry_over(said, history)
    asked, answers = [], [{"reply": "¡Claro!", "steps": [], "go_ahead": True, "claims_making": False},   # said yes, planned nothing
                          {"reply": "Un plano del cachorro.", "steps": [dict(SHOT, name="Puppy", prompt="A puppy runs across a lawn.")],
                           "go_ahead": True, "claims_making": True}]

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        asked.append(message)
        return answers.pop(0)
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    plan = client.post("/api/agent/plan", json={"instruction": "hazlo", "history": history}).json()
    assert "A puppy runs across a lawn" in asked[0]
    assert len(asked) == 2 and agent.NO_STEPS in asked[1]   # asked again, once, to plan what it approved
    assert [s["name"] for s in plan["steps"]] == ["Puppy"]


def test_a_reply_in_hindi_that_claims_work_without_a_plan_is_caught(client, monkeypatch):
    from scene import agent
    register(client)
    asked = []

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        asked.append(message)
        return {"reply": "मैं इसे अभी बना रहा हूँ।", "steps": [], "claims_making": True, "wants_sound": False, "go_ahead": False}
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    plan = client.post("/api/agent/plan", json={"instruction": "एक कुत्ते का वीडियो बना दो"}).json()
    assert len(asked) == 2 and plan["reply"] == agent.EMPTY_CLAIM and plan["steps"] == []


def test_sound_and_a_split_asked_in_spanish_are_made(client, monkeypatch):
    import asyncio
    from scene import media
    me = register(client)
    db = client.app.state.db
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    asyncio.run(media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d=6:r=24", "-pix_fmt", "yuv420p", folder / "clip.mp4"))
    clip = db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, seconds, size, created) "
                  "VALUES (?, 'x/y', 'video', 'Clip', 'clip.mp4', '', '{}', '{}', 6, 1, 1)", (me["id"],))
    db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, seconds, size, created) "
           "VALUES (?, 'x/y', 'audio', 'Tune', 'tune.mp3', '', '{}', '{}', 1, 1, 2)", (me["id"],))
    answers = [{"reply": "No puedo hacerlo.", "steps": [], "wants_sound": True, "claims_making": False, "go_ahead": False},
               {"reply": "En tres partes.", "steps": [{"tool": "trim", "source": clip, "start": 0, "end": 2, "parts": 3}],
                "wants_sound": False, "claims_making": True, "go_ahead": False}]

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        return answers.pop(0)
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    # the model said it wants sound, though it only talked: the step is made anyway
    sound = client.post("/api/agent/plan", json={"instruction": "ponle la música al vídeo"}).json()["steps"]
    assert sound and sound[0]["sound"]["video"] == clip
    # a trim with "parts" 3 is the split into three that was asked for, in words no English check knows
    pieces = client.post("/api/agent/plan", json={"instruction": "divídelo en tres", "selection": [clip]}).json()["steps"]
    assert [s["name"] for s in pieces] == ["Clip part 1 of 3", "Clip part 2 of 3", "Clip part 3 of 3"]
