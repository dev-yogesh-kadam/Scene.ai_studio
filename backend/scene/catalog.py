"""The workflow catalog: every model the studio offers, as a workflow (providers/workflows.py). A model is offered by a
provider whose key has it: a Scene provider over the v1 contract (Studio_automation), or On this PC (the studio's own
tools). Its id is "<folder>/@<model id>" ("video/@seedance_2_5", "audio/@transcribe").

The studio once ran ComfyUI workflow files from workflows/<kind>/; they are kept in workflows/archive/ and never read."""

from .comfy import workflows

KINDS = ("video", "image", "audio")
# The folders a model is offered in. An upscaler makes nothing from a prompt: it takes a video the user has and returns
# it larger, so it is its own action in the studio and is left out of the Create page and the agent's workflows.
FOLDERS = (*KINDS, "upscaler")


class Catalog:
    def __init__(self, providers=None):
        # The providers' models offered as workflows (providers/workflows.ProviderWorkflows; main.py sets it).
        self.providers = providers

    async def known(self, workflow_id):
        """Whether a workflow id is one offered now (the providers' models read first when due: right after a start
        the list in hand is empty)."""
        if self.providers is None:
            return False
        await self.providers.refresh()
        return workflow_id in self.providers.workflows()

    def is_provider(self, workflow_id):
        from .providers.workflows import is_provider_id
        return is_provider_id(workflow_id)

    def current(self, workflow_id):
        """The id a workflow goes by now: a model keeps its id for good (the contract never reuses one)."""
        return workflow_id

    async def load(self, workflow_id):
        if self.providers is not None and self.is_provider(workflow_id):
            await self.providers.refresh()
            wf = self.providers.get(workflow_id)
            if wf is not None:
                return wf
            raise workflows.WorkflowError("{} is not offered now: no provider key in use has it.".format(workflow_id))
        raise workflows.WorkflowError("There is no workflow named '{}': the studio's models come from its providers "
                                      "(Servers & APIs → Providers).".format(workflow_id))

    async def listing(self):
        if self.providers is None:
            return []
        await self.providers.refresh()
        items = []
        for workflow_id, wf in self.providers.workflows().items():
            profile = wf["profile"]
            listed = profile.get("refs") if isinstance(profile.get("refs"), dict) else {}
            items.append({"id": workflow_id, "kind": workflow_id.split("/", 1)[0], "title": profile["title"],
                          "description": profile.get("description", ""), "source": "generation", "provider": True,
                          "model": profile["provider"]["model"],
                          "picture_refs": int(listed.get("max", 0)) + len([r for r in profile.get("optional_refs", [])
                                                                           + profile.get("required_refs", []) if r.endswith(":image")])})
        return items
