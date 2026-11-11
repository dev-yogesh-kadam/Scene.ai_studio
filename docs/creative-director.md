# The creative director

The studio's agent used to be a careful production assistant: its system prompt was almost all mechanics. It is now a
senior creative director who thinks about intent, audience, one idea, a hook and restraint, has a point of view,
knows film, advertising, social-video and design craft, and measures its own work. What did not change: **the model only
proposes**; the server checks and prices every step; nothing runs until the user clicks Approve; every guardrail of
`guardrails.py` still holds; Claude is reached through Claude Code (`claude.py`), not the API.

## The identity and the process

`SYSTEM` in `backend/scene/agent.py` is in nine tagged sections, in this order: `<who_you_are>`, `<how_you_work>`,
`<talking_with_the_user>`, `<what_the_studio_does>`, `<neuralcore>`, `<attached_items>`, `<tools>`,
`<rules_for_a_plan>`, `<what_you_keep_to_yourself>`. Each keeps a plain heading line inside its tag.

- **Who you are**: intent first (who it is for, where it is seen, what the viewer should feel or do); one idea per piece,
  said in one sentence before any shots; a point of view in one line, never a lecture; restraint; the craft (a hook in
  the first 1-2 s for social, coverage, screen direction, motivated camera, light and colour for the mood, pacing with
  the music); honest judgement about what the models do badly; and the user's word always wins.
- **How you work**: small jobs get no questions; big jobs get a brief, a concept, stills first and a second opinion;
  open briefs get 2-3 directions as one question card, each with a one-line pitch and a default.
- **Explain mode** (`EXPLAIN`) lets the director teach the craft reason behind a choice. `REVIEW`, `SECOND_OPINION` and
  `GRADE` share `CRAFT_VALUES`, so every judge of the work uses the same values.
- The system prompt is the same for every message of a conversation (a Claude session reopens when it changes): what
  changes per message (the craft note, the examples, the brief) goes in the message.

## The big-job threshold

`agent.big_job(steps, instruction, history, credits)` is the one place it is decided. A plan is a big job when it has
**more than 4 generate steps** (a shot's variations count once; edits and the cut never), when it is priced above the
guardrail **`creative_big_job_credits`** (default 600 credits, 0 to 10,000,000, on the console's Guardrails card; 0
means by shots alone), or when the message asks for more than 4 shots ("a 20-shot ad").

What a big job gets, in the server's finishing check (`creative` in `api/workspace.py`); inside a long skill's run
the same process is fitted to the skill's stages (next section):

1. **The brief.** With no `/brief` in the conversation's memory (a conversation without memory keeps it as a
   `Brief:` line of the direction), the plan is sent back **once** to ask one brief card first: `questions`, at most 4,
   each with a default (audience, platform and shape, tone, a reference or must-have). When the user's messages already
   answer them, the model writes `/brief` itself.
2. **Then, once, the studio's notes in one hint**: the concept if it is missing (a required `concept` field of the
   answer, one sentence, kept at `/concept` and returned with the plan), **stills first** for a big video job (one
   picture per character or scene, unless NeuralCore already keeps approved stills or the user said to skip them), the
   quality gates (below), and **an automatic second opinion**: the server calls `second_opinion` itself (the tool's own
   code) and gives the critique back as "A senior creative director reviewed your plan: ... Revise if it helps; you
   decide." At most once a message; written down as `second_opinion (auto)` in the agent's calls and in the session's
   story, and in Langfuse with the metadata `charged: false` and the run. **The studio pays for it**: it is never
   charged to the user's credits (the `second_opinion` tool the agent calls on the user's behalf still is). The choice
   **`creative_auto_review`** (on / off, default on, the Guardrails card) switches it off to save Claude usage.

All of these are hints, never blocks: the model decides, and the user still approves.

### Inside a long skill's run

Most "make a video of …" messages run the default skill, script-to-video, which has stages and questions of its own.
The process fits into them (`in_run` in `api/workspace.py`), each hint once a run, the run's own marks kept at
`/studio/...` of its state (studio-only, like `/skill`):

- **Brief.** While `/brief` is empty, the skill's setup card must ask the brief's fields too (`agent.brief_missing`
  reads the card's questions and options). A card that leaves two or more out is sent back once to fold them into that
  same card, never a second one, at most `MAX_QUESTIONS` together, leaving out what the message or the skill's inputs
  already answer. Once the card is answered, a turn that has not saved `/brief` is told once to save it.
- **Concept.** The first write of a shot plan (`agent.SHOT_PLAN`: `/director/episode`, `/director/scenes/...`,
  `/s2v/clips`, `/plan/...`) is refused once until `/concept` holds one sentence; a plan of video shots with no concept
  gets the concept note.
- **Review.** Once the run has a shot plan, the automatic second opinion reads it (with the brief and the concept) and
  gives its critique once; the run is marked (`auto_opinion`, with the model) so it never runs twice in one run.
- **Stills first** only for a big job whose skills make no anchors or key stills themselves (`agent.makes_stills`):
  script-to-video's anchors already are.
- The **quality gates** and the **content check** run as outside a run.
- `SKILL_RULES` says this in four lines; no skill file was changed.

The **director skill** (`skills/director.md`, `auto: story`) now loads on its own for multi-shot film and story work
(`skills.wants_directing`): a story, a script, a short film, a scene of several shots, a music video. Never for a single
shot, an edit or motion graphics, never beside a long skill the user named (that skill calls it), and never as a run's
skill or one checked before it starts.

## The craft library and the gold examples

- **Craft notes** (`backend/scene/craft/*.md`): 14 short, practical notes, each with `id`, `title`, `tags` and a
  one-line `when`: hooks for social video, ad structures, shot grammar and coverage, screen direction and continuity,
  camera moves, lighting, colour and grading, pacing and cutting to music, genre conventions, product hero shots,
  character consistency, typography and motion graphics, platform specs, and what the models do badly with the
  workarounds. They point to `scene_presets/`, `scene_recipes/`, `prompters/` and `skills/` instead of repeating them.
- **craft_search** (a tool, `agent_tools.py`) ranks them with BM25 in Python (`craft_library.py`) and gives the best
  one to three, through `agent.fit_result`. A message that looks like a big job (`agent.looks_big`: an ad, a film, a
  reel, a campaign, in English, Hindi or Spanish, or more than 4 shots) carries the best note's title and `when` line.
- **Gold examples** (`backend/scene/gold/*.json`): 25 briefs answered to a senior creative's standard, each with
  `brief`, `context` (platform, audience), `concept`, `plan_outline` (one line a shot: size, angle, move, place,
  action), `why` (the craft reasons) and `tags`. The two closest go with a big job's message as "Examples of strong
  work (adapt, never copy)".
- **How a human approves them.** Every example starts as `"status": "draft"`. A human creative reads each, edits it, and
  sets `"approved"` or `"rejected"`. Drafts and approved ones are used; a rejected one never is. Candidates harvested from
  real use (below) wait in `gold/candidates/`, which the loader never reads: moving one up into `gold/` is a human's act.

## The content check

`content_check.py`: one call to the fast model over every plan's prompts and drawn words, in any language, before it is
shown for Approve. It flags a real person's likeness without the user's own reference, sexual content or anything
involving minors, trademarks the user did not supply, copyrighted characters or a recreation of an existing film, game
or show, and hate, harassment or violence beyond a film rating. The setting `content_check_mode` (off / **warn** /
block) decides what it does: in block mode a `block` refuses the plan plainly, and a `warn` is one line on the plan
card. Every flag is a row of the `moderation` table. **It fails open**: if the check's own call fails, the plan goes on
unchecked, the error is logged and the console's Checks card shows it. The word list in `moderation.py` is unchanged.
See [guardrails.md](guardrails.md), sections 4 and 6 (the quality gates: continuity, shot variety, a hook for social
video, no words asked of a video model).

## The rubric and calibration

[creative-rubric.md](creative-rubric.md): six marks, 1 to 5 (idea, hook, craft, fit, prompt quality, honesty).
`evals/cases/creative.json` holds 20 creative cases (open briefs, ads, reels, drama, Hindi and Spanish briefs, and
traps: words inside a video, a real celebrity, a 20-shot request with no detail). In live mode an Opus judge marks each
plan and fails a case below 3 on any mark; in replay the same cases check their structure (a brief asked, a concept
given, the examples retrieved). `python -m evals.calibrate` puts the judge next to your own marks. In production a
share of turns (`langfuse_grade_share`) is graded by the fast model with the same rubric, as Langfuse scores
`creative-idea` … `creative-honesty` beside `claude-grade`; never charged to the user. See [evals.md](evals.md).

## The harvest loop

Real feedback reaches Langfuse as scores on the turn that made the work: `user-thumb` (a thumb: 1 up, 0 down,
key `rating-<item>`, so a thumb turned over replaces the old one), `approved` (a plan approved, a still animated: 1; a
finished shot asked again: 0), `retaken` (a shot made again, after a failed review or by the user: 1) and `review` (the
review's verdict: 1 fine, 0.5 minor, 0 major).

`python -m evals.harvest` reads those signals for recent turns (from Langfuse when it is set; else the same signals
from the studio's tables: approved plans, their items' ratings, retakes and reviews, and the message before each). A
liked or approved turn becomes a candidate gold example (`status: draft`) in `gold/candidates/`; a disliked, retaken or
badly reviewed one becomes a candidate eval case in `evals/cases/candidates/`. A bad signal wins over a good one.
Nothing enters the live sets on its own: a human reviews each candidate, fills in what is missing (a gold example's
`why`, an eval case's `expect`) and moves it over. The loop: use → harvest → review → the examples and the evals grow →
the prompt and the craft notes are tuned against them.

## No fine-tuning, and why

The studio does not fine-tune a model, and does not plan to. Claude is reached through Claude Code on the owner's
account, which offers no fine-tuning; the models improve every few months, and a tuned copy would be left behind; and
taste here is mostly knowing *what to do for this brief*, which changes with every brief and every user. So taste is
built the way a studio trains a junior: a clear identity and process (the prompt), the craft written down (the notes,
found by retrieval when they matter), worked examples of strong work (the gold set, reviewed by a person), checks that
send weak work back once (the gates and the second opinion), and measurement (the rubric, the evals, calibration and
the Langfuse scores). Each of those can be read, changed and tested in an afternoon; a fine-tuned model can be none of
them.
