"""ComfyUI as a provider: a wrapper of the code that has always rendered (comfy/client.py, comfy/workflows.py and the
load balancer, balancer.py). Nothing about a ComfyUI render changes.

ComfyUI has no keys of its own (a server may sit behind a proxy that wants one: the key is then kept as before) and no
list of models: its "models" are the studio's ComfyUI workflows, those this server takes (its Workflows patterns,
balancer.py), each with a capability from its folder and file name (CAPABILITY). The render itself still goes through
jobs.py and the balancer, which already pick a server, send the files, follow the progress and fetch the results; the
router only names the ComfyUI provider it would use (shadow) or leaves ComfyUI's workflows to the balancer (on).
"""

import fnmatch

import httpx

from .base import Adapter, ProviderProblem, RequestProblem
from ..comfy import workflows
from ..comfy.client import Comfy, ComfyError

# (folder, file-name pattern) -> capability, the first that fits.
CAPABILITY = (
    ("upscaler", "*", "upscale_video"),
    ("audio", "*transcribe*", "transcribe"),
    ("audio", "*separate*", "separate_voice"),
    ("audio", "*music*", "music"),
    ("audio", "*speech*", "speech"),
    ("audio", "*sound_effect*", "sound_effect"),
    ("audio", "*", "speech"),
    ("video", "*lipsync*", "lip_sync"),
    ("video", "*v2v*", "video_to_video"),
    ("video", "*outpaint*", "outpaint"),
    ("video", "*animate*", "animate"),
    ("video", "*talking_head*", "talking_head"),
    ("video", "*", "text_to_video"),
    ("image", "*", "image"),
)


def capability_of(workflow_id):
    folder, _, name = str(workflow_id or "").partition("/")
    for want, pattern, capability in CAPABILITY:
        if folder == want and fnmatch.fnmatchcase(name, pattern):
            return capability
    return ""


def input_schema_of(schema):
    """A JSON Schema of what a ComfyUI workflow takes, from its presets (workflows.describe): its controls, options and
    reference slots. Only for the console and the router's list: a ComfyUI render is still built from the schema."""
    properties, required = {}, []
    for control in schema.get("controls") or []:
        kind = {"text": "string", "string": "string", "int": "integer", "float": "number", "bool": "boolean"}.get(control["type"], "string")
        entry = {"type": kind, "title": control["label"]}
        if control.get("default") is not None:
            entry["default"] = control["default"]
        if control.get("choices"):
            entry["enum"] = list(control["choices"])
        properties[control["id"]] = entry
        if control.get("role") == "prompt" and not schema.get("prompt_optional"):
            required.append(control["id"])
    for option in schema.get("options") or []:
        properties[option["id"]] = {"type": "string", "title": option["label"], "default": option.get("default"),
                                    "enum": [c["id"] for c in option.get("choices") or []]}
    for ref in schema.get("refs") or []:
        properties[ref["id"]] = {"type": "string", "format": "uri", "title": ref["label"], "x-scene-file": ref["kind"]}
        if ref.get("required"):
            required.append(ref["id"])
    return {"type": "object", "properties": properties, "required": required}


class ComfyUI(Adapter):
    kind = "comfyui"

    def __init__(self, base_url="", catalog=None, patterns=()):
        super().__init__(base_url)
        self.catalog = catalog         # the studio's workflows (catalog.Catalog)
        self.patterns = list(patterns)  # the Workflows this server takes (endpoints.models), [] for any

    async def whoami(self, key):
        client = Comfy(lambda: self.base_url)
        try:
            stats = await client.stats()
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderProblem("ComfyUI did not answer ({}).".format(type(error).__name__))
        finally:
            await client.http.aclose()
        devices = stats.get("devices") or [{}]
        return {"key": {"label": "", "max_concurrent": None},
                "provider": {"name": "ComfyUI", "version": str((stats.get("system") or {}).get("comfyui_version") or "")},
                "device": str(devices[0].get("name") or "")}

    async def models(self, key):
        """The ComfyUI workflows this server takes (not the generation server's), each as a model."""
        from ..balancer import matches
        found = []
        if self.catalog is None:
            return found
        for item in await self.catalog.listing():
            if item.get("error") or item.get("source") != "comfy" or item.get("provider"):
                continue
            if self.patterns and not matches(self.patterns, item["id"]):
                continue
            capability = capability_of(item["id"])
            if not capability:
                continue
            try:
                schema = workflows.describe(await self.catalog.load(item["id"]))
            except workflows.WorkflowError:
                continue
            found.append({"id": item["id"], "name": item["title"], "capability": capability,
                          "best_for": schema.get("pick_when") or item.get("description") or "",
                          "input_schema": input_schema_of(schema), "limits": {}, "pricing": {},
                          "typical_seconds": None, "can_cancel": True})
        return found

    async def start(self, key, model, input, metadata, idempotency_key):
        # ComfyUI renders are built and sent by jobs.py (the graph, its files, its chain of clips): never through here.
        raise RequestProblem("A ComfyUI render is sent by the studio's queue, not by the provider router.")

    async def status(self, key, job_ref):
        client = Comfy(lambda: self.base_url)
        try:
            found = await client.history(job_ref)
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderProblem("ComfyUI did not answer ({}).".format(type(error).__name__))
        finally:
            await client.http.aclose()
        state = (found or {}).get("status") or {}
        if state.get("status_str") == "error":
            return {"status": "failed"}
        return {"status": "succeeded" if state.get("completed") else "running"}

    async def cancel(self, key, job_ref):
        client = Comfy(lambda: self.base_url)
        try:
            await client.cancel(job_ref)
        except (httpx.HTTPError, ComfyError):
            pass
        finally:
            await client.http.aclose()
        return {"status": "cancelled", "charged": False}
