"""Ops and reliability (hardening pass, 10 Nov 2026): the health checks (database, Claude Code signed in, FFmpeg,
HyperFrames), the JSON logs cleaned of keys, the daily backups by the calendar, and the Docker files."""

import asyncio
import io
import json
import os
import re
import sys

import pytest

from scene import backup, health, media, motion, phone
from scene.db import offload
from scene.config import ROOT
from scene.logs import LONGEST, JsonLines
from test_api import console, register


# ---------------------------------------------------------------- JSON logs

def _logged(*writes):
    out = io.StringIO()
    stream = JsonLines(out, "error")
    for text in writes:
        stream.write(text)
    return [json.loads(line)["message"] for line in out.getvalue().splitlines()]


def test_a_json_log_line_never_holds_a_key_a_token_or_a_password():
    key = "sk-ant-api03-" + "A1b2C3d4" * 6
    lines = _logged("Claude failed with key {}\n".format(key),
                    "could not connect: postgresql://scene_app:hunter2-very-secret@localhost:5432/scene\n",
                    'the reply was {"api_key": "zz-abcdef123456"}\nAuthorization: Bearer ' + "q" * 40 + "\n")
    said = "\n".join(lines)
    for secret in (key, "hunter2-very-secret", "zz-abcdef123456", "q" * 40):
        assert secret not in said
    assert lines[0].startswith("Claude failed with key ") and "[redacted]" in lines[0]
    assert "postgresql://scene_app:[redacted]@localhost:5432/scene" in lines[1]   # where it was, without the password


def test_a_json_log_line_keeps_ordinary_words_and_cuts_a_huge_one():
    assert _logged("Scene.ai is running at http://localhost:8080\n") == ["Scene.ai is running at http://localhost:8080"]
    huge = _logged("A failure that quotes a whole prompt: " + "word " * 5000 + "\n")[0]
    assert len(huge) < LONGEST + 80 and huge.endswith("more characters not logged]")

