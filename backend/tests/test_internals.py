"""What a user is shown of the agent's workings (internals.py): as they are for an admin or an Insider, in plain words
for everyone else."""

import asyncio

from scene import internals, staff


def test_an_admin_and_an_insider_see_the_workings_and_a_user_does_not():
    assert internals.shown_to({"role": "admin"}) and internals.shown_to({"role": "insider"})
    assert not internals.shown_to({"role": "user"}) and not internals.shown_to({"role": "support"}) and not internals.shown_to(None)
    assert "internals" in staff.AREAS and staff.sees("insider", "internals") and not staff.sees("finance", "internals")


def test_the_rows_of_work_say_no_skill_neuralcore_session_or_tokens():
    titles = internals._titles()
    rows = [{"type": "activity", "icon": "skill", "text": "Read the skill “Script to Video”"},
            {"type": "activity", "icon": "skill", "text": "Carried on with “Script to Video”, the skill of this run"},
            {"type": "activity", "icon": "book", "text": "Opened NeuralCore: 1 entry"},
            {"type": "activity", "icon": "book", "text": "Went on with this conversation's Claude session: sent only what is new"},
            {"type": "activity", "icon": "plan", "text": "Checked and priced 8 steps"},
            {"type": "activity", "icon": "info", "text": "Read 70,357 tokens (67,123 from the cache) and wrote 6,887"},
            {"type": "thought", "text": "The script-to-video skill wants the sheets first; a short film needs a director's eye."}]
    shown = internals.plain_log(rows, titles)
    texts = [r["text"] for r in shown]
    assert texts[:4] == ["Used a skill", "Checked the project's references", "Picked up the conversation", "Checked and priced 8 steps"]
    assert not any("token" in t or "NeuralCore" in t or "Claude" in t or "Script to Video" in t for t in texts)
    # A skill's id is taken out of a thought; plain words that are also names of skills ("short film", "director") stay.
    assert "script-to-video" not in texts[4] and "a short film" in texts[4] and "director" in texts[4]


def test_a_plan_streamed_to_a_user_is_in_plain_words_and_to_an_admin_as_it_is():
    async def events():
        yield {"type": "activity", "icon": "skill", "text": "Read the skill “Script to Video”"}
        yield {"type": "activity", "icon": "skill", "text": "Loaded the skill “Script to Video”"}
        yield {"type": "plan", "reply": "Done.", "thought": "", "activity": [{"type": "activity", "icon": "info", "text": "Read 9 tokens"}]}

    async def collect(user):
        return [e async for e in internals.for_user(events(), user)]

    plain = asyncio.run(collect({"role": "user"}))
    assert [e.get("text") for e in plain[:-1]] == ["Used a skill"] and plain[-1]["activity"] == []
    whole = asyncio.run(collect({"role": "admin"}))
    assert whole[0]["text"] == "Read the skill “Script to Video”" and whole[-1]["activity"][0]["text"] == "Read 9 tokens"
