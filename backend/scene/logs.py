"""The studio's output as JSON lines (`log_format: "json"`), for Azure Monitor and other log stores: each line the
app prints becomes {"time", "level", "message", "process"}. Off by default: the console's plain lines, as always."""

import json
import os
import sys
import time


class JsonLines:
    """A stream that writes each whole line it is given as one JSON object."""

    def __init__(self, stream, level):
        self.stream, self.level, self.pending = stream, level, ""

    def write(self, text):
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.stream.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
                                              "level": self.level, "message": line, "process": os.getpid()}) + "\n")
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
