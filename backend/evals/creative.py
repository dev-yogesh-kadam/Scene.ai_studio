"""The creative evals' judge (docs/evals.md, docs/creative-rubric.md): the strongest Claude there is (Agent.stronger(),
an Opus) marks a plan against the creative rubric, each mark 1 to 5, and the check `creative` fails a case below its
threshold for any mark. It runs in live mode only: a replayed answer is the case's own, and judging it says nothing of
the model. In replay the creative cases check their structure instead (`brief_asked`, `concept`, `examples`)."""

from scene import agent as agent_module

MARKS = agent_module.RUBRIC_MARKS
THRESHOLD = 3   # the lowest mark that passes, for every mark a case does not set itself

JUDGE = """You are a senior creative director at an AI image and video studio, judging the work of the studio's own
creative director for the people who build it. You are given the user's brief, the conversation's notes, and what the
studio answered: its reply, its concept, the question card it asked (if any) and each step of its plan. Mark it against
the creative rubric below, each mark 1 to 5, honestly: 3 is competent, 5 is work you would put your name to. "why":
two or three plain sentences on the strongest and the weakest part.

""" + agent_module.CREATIVE_RUBRIC

SHAPE = {"type": "object", "required": [*MARKS, "why"], "properties": {
    **{k: {"type": "integer", "minimum": 1, "maximum": 5} for k in MARKS}, "why": {"type": "string"}}}


def plan_text(case, plan):
    """What the judge reads: the brief and the plan, in words."""
    ask = case.get("ask") or {}
    lines = ["The user's brief: {}".format(ask.get("instruction") or ""),
             "The conversation's notes: {}".format(ask.get("direction") or "(none)"),
             "The reply: {}".format(plan.get("reply") or "(none)"),
             "The concept: {}".format(plan.get("concept") or "(none)")]
    for q in ([plan["question"]] if plan.get("question") else []) + list(plan.get("questions") or []):
        lines.append("A question asked: {} Options: {}{}".format(
            q.get("text"), "; ".join(q.get("options") or []),
            " ({})".format("; ".join(d for d in q.get("details") or [] if d)) if any(q.get("details") or []) else ""))
    for n, step in enumerate(plan.get("steps") or [], start=1):
        settings = step.get("settings") or {}
        lines.append("Step {}: {} [{}{}] {}".format(
            n, step.get("name"), step.get("kind"), ", " + str(settings.get("workflow")) if settings.get("workflow") else "",
            " ".join(str(step.get("prompt") or settings.get("prompt") or "").split())[:900]))
    if not plan.get("steps"):
        lines.append("(No steps: the studio talked or asked.)")
    return "\n".join(lines)


async def judge(brain, case, plan):
    """The judge's marks of a plan: {"marks": {mark: 1..5}, "why", "model"}. brain: an Agent with Claude (live)."""
    model = await brain.stronger()
    answer = await brain.chat([{"role": "system", "content": JUDGE}, {"role": "user", "content": plan_text(case, plan)}], SHAPE,
                              model=model, purpose="creative judge")
    marks = agent_module.rubric_marks(answer)
    if len(marks) != len(MARKS):
        raise agent_module.AgentError("The judge left out a mark: {}".format(", ".join(m for m in MARKS if m not in marks)))
    return {"marks": marks, "why": " ".join(str(answer.get("why") or "").split())[:800], "model": answer.get("_model")}


def thresholds(want):
    """The lowest passing mark of each mark: `want` is true (THRESHOLD for all) or {mark: lowest} (the rest THRESHOLD)."""
    given = want if isinstance(want, dict) else {}
    return {m: int(given.get(m, THRESHOLD)) for m in MARKS}


def below(marks, want):
    """The marks under their threshold: [(mark, given, lowest)]."""
    lowest = thresholds(want)
    return [(m, marks.get(m), lowest[m]) for m in MARKS if marks.get(m) is None or marks[m] < lowest[m]]
