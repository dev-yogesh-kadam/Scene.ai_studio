"""What every provider adapter is: one small async interface, and the three kinds of problem a call can have.

A provider is a service the studio calls, with one address and one adapter (its `kind`); a key is a credential for one
provider, and a provider can have many. The router (router.py) picks a key for each call and decides what a problem
means from its kind alone:

- KeyProblem: this key can't do it now (bad key, no credit, rate limited, not in its scope). The key is cooled down and
  the next key is tried, once.
- ProviderProblem: the provider can't do it now (down, 5xx, the model unavailable). The next provider offering the same
  model is tried, once.
- RequestProblem: the request itself is refused (invalid, content refused). Never retried: the job fails with the
  provider's own words.

Nothing here knows ComfyUI, the generation server or Claude: each adapter (v1.py, comfyui.py, anthropic_api.py, local.py) maps
its own answers onto these. Claude on this PC (claude_local) has no adapter: it has no key to check,
and its status is claude_connection.status's. Keys are passed in, never kept by an adapter, and never logged."""

KINDS = {
    "scene_provider_v1": "Scene provider (v1)",
    "comfyui": "ComfyUI",
    "claude_local": "Claude on this PC",
    "anthropic": "Anthropic",
    "local_tools": "On this PC",
}
# The providers whose models are offered as workflows (providers/workflows.py) and run by the queue: Scene providers over
# the v1 contract, and the tools on this PC (local.py), which answer the same way.
MODEL_KINDS = ("scene_provider_v1", "local_tools")
BUILT_IN = ("local_tools",)   # made by the studio (migration 0018), one only: not added, given keys or removed in the console
CLAUDE_KINDS = ("claude_local", "anthropic")   # the providers the agent's model can come from
KEYLESS = ("claude_local",)   # no key and no address: Claude on this PC uses the account Claude Code is signed in with
SELF_HOSTED = ("scene_provider_v1", "comfyui")   # asked for an address once; Anthropic's is known

# The capabilities of the contract (02-provider-api-v1.md) and the folder of workflows/ each one's models are offered
# in. agent_llm is the agent's model (Claude on this PC, Anthropic): never a workflow. One the studio doesn't know is ignored.
CAPABILITY_FOLDERS = {
    "text_to_video": "video", "lip_sync": "video", "upscale_video": "upscaler",
    "video_to_video": "video", "outpaint": "video", "animate": "video", "talking_head": "video",
    "image": "image", "upscale_image": "image", "control_map": "image",
    "speech": "audio", "music": "audio", "sound_effect": "audio", "transcribe": "audio", "separate_voice": "audio",
}
# Each capability in words, in the order the console lists them ("What makes what", registry.coverage).
CAPABILITY_WORDS = {
    "text_to_video": "Video", "image": "Pictures", "speech": "Voiceover", "music": "Music", "sound_effect": "Sound effects",
    "lip_sync": "Lip sync", "upscale_video": "Video upscale", "upscale_image": "Picture upscale",
    "control_map": "Control maps", "transcribe": "Transcription", "separate_voice": "Voice separation",
    "talking_head": "Talking head", "video_to_video": "Video to video", "outpaint": "Outpaint", "animate": "Character animation",
}
AGENT_LLM = "agent_llm"
STATUSES = ("ok", "invalid", "no_credit", "rate_limited", "unknown")


class ProviderError(Exception):
    """A provider call that didn't work. `request_id` is the provider's X-Request-Id when it sent one."""

    def __init__(self, message, request_id="", code=""):
        super().__init__(message)
        self.request_id = request_id or ""
        self.code = code or ""


class KeyProblem(ProviderError):
    """The key can't do it now. `status` is what the key is marked (invalid, no_credit, rate_limited, or "" when the key
    is fine but lacks this model: not_allowed), `retry_after` the seconds the provider asked to wait, or None."""

    def __init__(self, message, status="", retry_after=None, request_id="", code=""):
        super().__init__(message, request_id, code)
        self.status = status
        self.retry_after = retry_after


class ProviderProblem(ProviderError):
    """The provider can't do it now: down, a 5xx, the model unavailable."""


class RequestProblem(ProviderError):
    """The request is refused as it is: never retried."""


class Adapter:
    """One provider kind. `base_url` is the provider's address ("" for Anthropic's, which the adapter knows)."""

    kind = ""

    def __init__(self, base_url=""):
        self.base_url = str(base_url or "").rstrip("/")

    async def whoami(self, key):
        """What this key is: {"key": {"label", "mode", "max_concurrent", "scopes", ...}, "provider": {"name", "version"},
        "credits": {...}, "alerts": [...]}, as much as the provider says."""
        raise NotImplementedError

    async def models(self, key):
        """The models this key may use: [{"id", "name", "capability", "input_schema", "limits", "pricing",
        "typical_seconds", "can_cancel", "best_for"}]."""
        raise NotImplementedError

    async def start(self, key, model, input, metadata, idempotency_key):
        """Start one job. Returns {"id" (the provider's job ref), "status", "quote", "request_id"}."""
        raise NotImplementedError

    async def status(self, key, job_ref):
        """Where a job is: {"status": queued|running|succeeded|failed|cancelled, "progress", "message", "outputs",
        "error"}."""
        raise NotImplementedError

    async def cancel(self, key, job_ref):
        """Stop following (and, where the provider can, stop) a job: {"status", "charged", "message"}."""
        raise NotImplementedError

    async def fetch_output(self, key, job_ref, n, target):
        """Write the job's output number `n` to the path `target`. Returns the output's description."""
        raise NotImplementedError

    async def close(self):
        pass


def last4(secret):
    """The last 4 characters of a key, the one part of it ever shown again."""
    secret = str(secret or "")
    return secret[-4:] if len(secret) >= 8 else ""
