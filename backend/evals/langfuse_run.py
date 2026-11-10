"""An eval run, kept in Langfuse as a dataset run: the cases are the items of the dataset "scene-agent-evals" (one per
case id, made again when a case changes), each result a trace of its own (a span, and a score "eval_passed" of 1 or 0
with what failed), linked to its item under the run's name. The traces and scores go the way the studio sends its own
(langfuse_trace.Sender); the dataset's items and the run's links are Langfuse's public API.

Langfuse is the one named by LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY: an eval run is not the studio,
so it never reads the studio's Servers & APIs. Nothing is sent unless --langfuse is given and all three are set."""

import base64
import os
import time

import httpx

from scene import langfuse_trace

DATASET = "scene-agent-evals"


def target_from_env(env=None):
    """(address, Authorization header) of the Langfuse named in the environment, or None."""
    env = os.environ if env is None else env
    url = (env.get("LANGFUSE_HOST") or "").rstrip("/")
    public, secret = env.get("LANGFUSE_PUBLIC_KEY") or "", env.get("LANGFUSE_SECRET_KEY") or ""
    if not (url and public and secret):
        return None
    return url, "Basic " + base64.b64encode("{}:{}".format(public, secret).encode("utf-8")).decode("ascii")


class _Sender(langfuse_trace.Sender):
    """The studio's sender, aimed at the eval's Langfuse instead of the studio's (it has no database here)."""

    def __init__(self, target):
        super().__init__(None)
        self._target = target

    def target(self):
        return self._target


def as_items(cases, results):
    """The run as langfuse_trace.dataset_run takes it: an item per case run, a result per item, in order."""
    by_id = {c["id"]: c for c in cases}
    items, done = [], []
    for result in results:
        case = by_id.get(result["id"]) or {}
        items.append({"key": "scene-eval-" + result["id"], "input": case.get("ask"), "expected": case.get("expect"),
                      "metadata": {"lang": case.get("lang"), "tags": case.get("tags") or [], "about": case.get("about") or "",
                                   "file": case.get("_file") or ""}})
        failed = ["{}: {}".format(n, f) for n, ok, f in result["checks"] if not ok]
        done.append({"key": "scene-eval-" + result["id"], "output": result.get("plan"), "seconds": result.get("seconds") or 0,
                     "scores": {"eval_passed": 1 if result["ok"] else 0}, "comments": {"eval_passed": "; ".join(failed)[:2000]},
                     "model": result.get("model") or ""})
    return items, done


async def send(target, run_name, cases, results, http=None):
    """Send a run's results. Returns how many results were linked to the run. http: a client to use (a test's).
    With the studio's own dataset functions (langfuse_trace.dataset_run, from the Langfuse area) they send it; on a
    tree without them, the same run is sent here."""
    studio_run = getattr(langfuse_trace, "dataset_run", None)
    if studio_run is not None:
        items, done = as_items(cases, results)
        sent = await studio_run(DATASET, items, done, run_name, description="The studio agent's eval cases (backend/evals/cases).",
                                metadata={"cases": len(results)}, target=target, http=http)
        return len((sent or {}).get("traces") or done)
    return await _send_here(target, run_name, cases, results, http)


async def _send_here(target, run_name, cases, results, http=None):
    url, auth = target
    headers = {"Authorization": auth}
    by_id = {c["id"]: c for c in cases}
    sender = _Sender(target)
    owned = http is None
    http = http or httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3))
    try:
        found = await http.get(url + "/api/public/v2/datasets/" + DATASET, headers=headers)
        if found.status_code == 404:
            made = await http.post(url + "/api/public/v2/datasets", headers=headers,
                                   json={"name": DATASET, "description": "The studio agent's eval cases (backend/evals/cases)."})
            made.raise_for_status()
        else:
            found.raise_for_status()
        runs = []
        for result in results:
            case = by_id.get(result["id"]) or {}
            item = await http.post(url + "/api/public/dataset-items", headers=headers, json={
                "datasetName": DATASET, "id": "scene-eval-" + result["id"], "input": case.get("ask"),
                "expectedOutput": case.get("expect"), "metadata": {"lang": case.get("lang"), "tags": case.get("tags") or [],
                                                                    "about": case.get("about") or "", "file": case.get("_file") or ""}})
            item.raise_for_status()
            run = "eval:{}:{}".format(run_name, result["id"])
            ended = time.time()
            failed = ["{}: {}".format(n, f) for n, ok, f in result["checks"] if not ok]
            sender.span("eval " + result["id"], ended - (result.get("seconds") or 0), ended, run=run,
                        metadata={"case": result["id"], "lang": result.get("lang"), "passed": result["ok"],
                                  "steps": len((result.get("plan") or {}).get("steps") or []), "total": (result.get("plan") or {}).get("total")},
                        fallback="Eval")
            sender.score(run, "eval_passed", 1 if result["ok"] else 0, comment="; ".join(failed)[:2000])
            runs.append((item.json().get("id") or "scene-eval-" + result["id"], run))
        await sender.send(http)   # the traces before the links that name them
        for item_id, run in runs:
            linked = await http.post(url + "/api/public/dataset-run-items", headers=headers, json={
                "runName": run_name, "datasetItemId": item_id, "traceId": langfuse_trace.trace_id(run)})
            linked.raise_for_status()
        return len(runs)
    finally:
        if owned:
            await http.aclose()
