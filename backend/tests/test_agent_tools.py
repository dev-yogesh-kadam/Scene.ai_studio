"""The agent's tools as Claude sees them (agent_tools.py): each described, with a valid input schema, in one place."""

import pytest

from scene import agent, agent_tools, edits


def test_every_tool_has_a_description_and_a_valid_schema():
    jsonschema = pytest.importorskip("jsonschema")
    offered = agent.native_tools(agent.TOOLS)
    assert set(offered) == set(agent.TOOLS) - {"finish"}
    for name, (about, schema) in offered.items():
        assert len(about) > 40 and "in your instructions." not in about, name   # its own words, not a pointer to them
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object" and set(schema.get("required") or []) <= set(schema["properties"]), name
    assert agent_tools.check() == []   # no property, however deep, without a description


def test_structured_fields_are_real_json_types():
    tools = agent_tools.TOOLS
    assert tools["film"][1]["properties"]["settings"]["type"] == "object"
    assert tools["timing"][1]["properties"]["settings"]["type"] == "object"
    assert tools["transcript"][1]["properties"]["value"]["type"] == "object"
    assert "type" not in tools["state_write"][1]["properties"]["value"]   # any JSON
    assert {"type": "object"} in [{"type": o["type"]} for o in tools["book_save"][1]["properties"]["settings"]["anyOf"]]
    # the fixed sets are enums
    assert tools["memory"][1]["properties"]["op"]["enum"] == ["remember", "recall", "forget"]
    assert "character" in tools["book_save"][1]["properties"]["op"]["enum"]
    # ...but not film's op: a session from before render_html and ffmpeg were tools still sends op "html" or "ffmpeg",
    # which the SDK would refuse with a bare "not one of [...]" before film could say what to call instead
    film_op = tools["film"][1]["properties"]["op"]
    assert "enum" not in film_op and set(agent_tools.FILM_OPS) == set(edits.FILM) - {"html", "ffmpeg"}
    assert all(op in film_op["description"] for op in agent_tools.FILM_OPS) and "trim" in agent_tools.FILM_OPS


def test_the_written_ops_are_tools_of_their_own():
    render, ffmpeg = agent_tools.TOOLS["render_html"][1], agent_tools.TOOLS["ffmpeg"][1]
    assert {"html", "width", "height", "duration", "fps", "format", "media", "project"} <= set(render["properties"])
    assert set(ffmpeg["required"]) == {"argv", "inputs", "outputs", "reason"}
    assert ffmpeg["properties"]["argv"]["type"] == "array"


def test_the_rules_keep_only_what_spans_tools():
    rules = agent.native_rules()
    assert "/cast/<name>" in rules and "$state:/folder/*" in rules and "Nothing is generated" in rules
    assert "same turn" in rules   # calls go together
    assert "- find_assets:" not in rules and "reference {\"image\"}" not in rules   # each tool's paragraph is with the tool
    assert "reference {\"image\"}" in agent_tools.TOOLS["film"][0]
    # the loop that faked tool calls with a "tool" field is gone: "finish" is no tool
    assert "finish" not in agent.TOOLS and not hasattr(agent, "tool_format") and not hasattr(agent, "CALL_FIELDS")


# ---------------------------------------------------------------- a tool's result is cut whole, never in the middle

def test_a_result_that_fits_is_given_as_it_is():
    for text in ("short", '[{"item": 1}]', '{"a": 1}', ""):
        assert agent.fit_result(text, 100) == text


def test_a_long_json_list_keeps_whole_items_and_says_how_many():
    import json
    items = [{"item": n, "name": "clip {}".format(n), "about": "x" * 40} for n in range(200)]
    cut = agent.fit_result(json.dumps(items), 1000)
    found = json.loads(cut)   # still JSON
    assert len(cut) <= 1000 and found[:-1] == items[:len(found) - 1]
    assert found[-1] == {"cut": True, "shown": len(found) - 1, "total": 200}


def test_a_long_json_object_keeps_whole_keys_and_says_how_many():
    import json
    record = {"key{}".format(n): "value " * 10 for n in range(100)}
    cut = agent.fit_result(json.dumps(record), 800)
    found = json.loads(cut)
    assert len(cut) <= 800 and found["_cut"] == {"shown_keys": len(found) - 1, "total_keys": 100}
    assert all(found[k] == record[k] for k in found if k != "_cut")


def test_long_text_is_cut_at_a_line_and_says_where_to_read_on():
    text = "\n".join("Line {}: the words of a page.".format(n) for n in range(1000))
    cut = agent.fit_result(text, 500, "web_fetch")
    shown = int(cut.rsplit("offset=", 1)[1].split()[0])
    assert len(cut) <= 500 and cut.startswith(text[:shown]) and text[shown] == "\n"   # whole lines only
    assert cut.endswith("[cut: showing {:,} of {:,} characters. Ask again with offset={} to read on.]".format(shown, len(text), shown))
    # a tool that takes no offset is told what is shown, not to ask again
    other = agent.fit_result(text, 500, "look")
    assert "of {:,} characters.]".format(len(text)) in other and "offset" not in other
    # one long line is cut at a space
    words = agent.fit_result("word " * 400, 300)
    assert words.split("\n")[0].endswith("word")
