"""The studio's output as JSON lines (`log_format: "json"`), for Azure Monitor and other log stores: each line the
app prints becomes {"time", "level", "message", "process"}. Off by default: the console's plain lines, as always.

A log store keeps what it is given for months and shows it to whoever may read the logs, so each line is cleaned first:
whatever looks like a key, a token or a password is replaced by [redacted] (the same `redact` as the spans sent to
Langfuse), and a line longer than LONGEST characters (an error that quotes a whole prompt or answer) is cut. The app
prints no user's words on purpose; this is for an error's text that carries them by accident.

Rotation is the log store's: docker-compose.yml caps Docker's own log files (json-file, max-size and max-file); on
Azure, Log Analytics keeps them for its workspace's retention."""

import json
import os
import sys
import time

from .langfuse_trace import redact

LONGEST = 2000   # characters of one line kept; the rest is said to be left out


def clean(line):
    """A line as it may be kept in a log store: no key, token or password in it, and at most LONGEST characters."""
    line = redact(line)
    if len(line) > LONGEST:
        line = line[:LONGEST] + " [… {:,} more characters not logged]".format(len(line) - LONGEST)
    return line


class JsonLines:
    """A stream that writes each whole line it is given as one JSON object."""

    def __init__(self, stream, level):
        self.stream, self.level, self.pending = stream, level, ""

    def write(self, text):
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                try:
                    message = clean(line)
                except Exception:   # a log line is never lost to its cleaning, nor let through uncleaned
                    message = "[a line that could not be cleaned, {:,} characters]".format(len(line))
                self.stream.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
                                              "level": self.level, "message": message, "process": os.getpid()}) + "\n")
        return len(text)

    def flush(self):
        self.stream.flush()

    def isatty(self):
        return False

    def __getattr__(self, name):
        return getattr(self.stream, name)


def configure(log_format):
    if (log_format or "").lower() == "json":
        sys.stdout = JsonLines(sys.stdout, "info")
        sys.stderr = JsonLines(sys.stderr, "error")
