# Guardrails

The studio's guardrails on spending, on the agent and on content: each one, where it lives in the code, the test that
tries to break it, and its setting. Written in the hardening pass of 10 November 2026 (branch `hard/guardrails`).

**The rule they keep:** the model only proposes; the server checks and prices; nothing runs until Approve; and nothing
costs more than was approved.

Most guardrails are small functions in `backend/scene/guardrails.py` (and `moderation.py`), each called by a one-line
hook in the file that does the work. The tests are in `backend/tests/test_guardrails.py`. A test marked
`xfail(strict=True, reason="needs hook-in: ...")` checks a hook that another area's file has to call; it fails
until that hook is wired, then its mark comes off. All the hooks are ready as one script, `guard_hooks.py` in the
hardening session's scratchpad (run from `backend/`), written against `studio-hardening` after the agent and database
merges; every one of its 28 edits finds its text there. Wired on `hard/guardrails`, the whole test file passed
(`pytest --runxfail tests/test_guardrails.py`: 52 passed) and so did the rest of the suite (661 passed).

Status column: **live** = works on the branch as it is; **hook** = the function and test are there, the one-line hook
is a request to the file's owner.

## Settings

All in the `settings` table, read through `db.setting` (shared cache: a change reaches every process at once, no
restart). Changed in the console through `GET/PUT /api/admin/guardrails` (hook, Backend API) or `guardrails.save`.

| Setting | Default | Range | What it limits |
|---|---|---|---|
| `guard_stop` | off | `{"since","by","text"}` | The studio-wide stop (kill switch) |
| `guard_plan_max` | 0 (none) | 0–10,000,000 credits | Credits one plan may reserve at approval (users; admins exempt) |
| `guard_run_max` | 0 (none) | 0–10,000,000 credits | Credits the renders of one run may cost together, less refunds |
| `guard_job_seconds` | 3600 | 10–86,400 s | The longest result one job is priced for |
| `guard_sessions_per_user` | 3 | 1–50 | Live Claude sessions one user may hold, of `claude.LIVE` = 6 |
| `guard_tool_calls` | 200 | 5–5,000 | Tool calls while answering one message |
| `guard_turn_seconds` | 3600 | 60–86,400 s | The longest one message to a live session may take |
| `daily_cap` (credits.py) | 0 (none) | per user too (`users.daily_cap`) | Credits one user may spend in 24 h |
| `moderation_words`, `moderation_mode` | `[]`, off | off / flag / refuse | Words the studio does not make |
| `creative_big_job_credits` | 600 | 0–10,000,000 credits (0: by shots alone) | A plan priced above this is a big job: the brief, the concept, the stills first, the automatic second opinion ([creative-director.md](creative-director.md)) |
| `content_check_mode` | warn | off / warn / block (a choice, `guardrails.CHOICES`) | What the content check does with a plan it flags (section 4) |
| `creative_auto_review` | on | on / off (a choice) | The automatic second opinion of a big job's plan and of a long run's shot plan; the studio pays for it, never the user ([creative-director.md](creative-director.md)) |

Fixed in code: `guardrails.MIN_SECONDS` = 1 (shortest priced length), `guardrails.TOOL_SECONDS` (per-tool time,
default 960 s, `web_fetch` 90 s, state and memory tools 60 s), `guardrails.MALFORMED_RETRIES` = 1,
`agent.TOOL_RESULT` = 8,000 / `SKILL_RESULT` = 40,000 characters, `agent.TOOL_ROUNDS` = 6 / `RUN_ROUNDS` = 40,
`agent.FIX_ROUNDS` = 2, `agent.MAX_STEPS` = 12, `agent.MAX_VARIATIONS` = 4, `workflows.MAX_CLIPS` = 8, plans at most
200 steps, `ffjob` limits (10 inputs, 5 sidecars, 4 outputs, 30–600 s).

## 1. The model only proposes; the server checks and prices

| Guardrail | Where | Test | Status |
|---|---|---|---|
| A step's workflow must exist and be switched on; it is priced as Generate prices it, before anything is charged | `plans.PlanRunner.price` → `catalog.load`, `studio.switched_on`, `studio.price` | `test_a_plan_step_with_a_made_up_workflow_is_refused_before_anything_is_charged` | live |
| Clip counts 1–8, choices from the workflow's list, at most 200 steps | `workflows.clip_count`, `workflows.context`, `plans.create` | `test_a_count_out_of_range_is_refused_at_the_estimate_and_in_a_plan` | live |
| A length that is not a number, under 1 s, or over `guard_job_seconds`, or a price below 0, is refused (a duration of −5 was priced at −100 credits, and the job then hit the `jobs_credits_not_negative` check as a 500) | `guardrails.check_quote`, hook at the end of `api/studio.py price()` | `test_a_negative_or_huge_length_is_refused_not_priced`, `test_quote_problem_...` | hook |
| **A plan's step never costs more than was approved.** A step paid from its plan's reservation may not draw more than is left of it; before, the rest came from the balance with the daily cap skipped | `guardrails.plan_step_problem`, hooks in `credits._cap_problem` (PREPAID branch, the early no) and `credits._charge_plan` (raises `OverCap`) | `test_a_plan_step_never_costs_more_than_was_approved`, `test_plan_step_problem_...` | hook |
| Only its owner sees, approves, resumes, stops a plan or chooses its takes | `plans.PlanRunner.get` (`user_id` in the query) | `test_a_plan_is_only_seen_approved_stopped_resumed_or_chosen_by_its_owner` | live |
| A plan approves itself (`auto`) only under the user's permission | `api/plans.approve_plan`, `preferences.runs_without_approve` | `test_a_plan_approves_itself_only_when_the_users_permission_says_so` | live |
| No agent tool queues a generation or charges for one; a made-up tool is not run | `agent_tools.TOOLS`, `claude._handlers` | `test_the_agents_tools_cannot_queue_a_render_or_spend` | live |
| An ffmpeg command reads and writes only in its own folder: no `..`, drive, root, share, protocol, device, `movie=` filter, shell word, or name that is not an input/sidecar/output; a concat list is checked too | `ffjob.check` (and `-protocol_whitelist file` at run) | `test_an_ffmpeg_command_cannot_write_or_read_outside_its_folder` (11 cases), `test_an_ffmpeg_concat_list_...` | live |

## 2. Spend limits

| Guardrail | Where | Test | Status |
|---|---|---|---|
| Daily cap per user | `credits.cap_problem` (Database area fixes its race) | existing credit tests | live |
| Per-plan maximum, at approval (and the stop) | `guardrails.plan_problem`, hook in `plans.PlanRunner.approve` after pricing | `test_a_plan_over_the_plan_limit_is_not_approved`, `test_the_plan_limit_holds_users_and_not_admins` | hook |
| Per-run maximum for long runs (a plan's steps are left to the plan limit) | `guardrails.run_problem(db, user_id, run, amount)`, hook in `studio.create_job` after `settings["run_of"]` | `test_the_run_limit_counts_what_a_run_spent_less_its_refunds`, `test_a_run_over_its_limit_is_refused_at_generate` | hook |
| **The stop (kill switch)**: no new agent turns, no new jobs (their credits given back), waiting renders do not start, running plans fail at their next step and give back the rest; no restart | `guardrails.stopped/set_stop/refuse_if_stopped/turn_check`; hooks in `jobs.JobManager.add` + `paused()`, `workspace.agent_plan`, `plans.approve`, and the console route | `test_the_stop_is_kept_...`, `test_the_stop_refuses_new_renders_...`, `test_the_stop_refuses_new_agent_turns`, `test_the_console_flips_the_stop_...` | hook |

The stop is different from maintenance mode (`health.maintenance`): maintenance refuses new jobs but lets agent
turns and waiting renders go on, and an admin's test run passes; the stop stops everything new.

## 3. Agent limits

| Guardrail | Where | Test | Status |
|---|---|---|---|
| Max model turns per message: `rounds + 2` (6 or 40 rounds), then `FINISH_NOW` | `agent.ask_with_tools`, `claude.converse` | existing (`test_agent_*`) | live |
| Max tool calls per message (`guard_tool_calls`) and a time per tool (`TOOL_SECONDS`) | `guardrails.run_tool`, hook in `claude._handlers.run` | `test_a_tool_call_past_the_limit_or_its_time_is_stopped`, `test_every_tool_..._how_long_it_may_take` | hook |
| A tool's result never passes its size, JSON stays JSON | `agent.fit_result` (applied in `claude._handlers` to every tool) | `test_a_tool_result_never_passes_its_size` | live |
| A cut outside text keeps its frame and note | `agent.fit_result` (hook: cut inside the frame) | `test_cutting_a_long_outside_text_keeps_its_frame` | hook |
| A silent turn is stopped: Claude Code quiet for `claude_timeout` while no tool runs (hard/agent's watchdog, `claude._next`); `guard_turn_seconds` is kept as an outer cap on a whole message, not wired (proposal) | `claude._turn` / `_next` | hard/agent's tests | live (watchdog) |
| One user holds at most `guard_sessions_per_user` live sessions: their oldest idle one closes first; all answering → refused | `guardrails.sessions_to_close`, hook in `claude.converse` before a new `_Live` | `test_one_user_holds_at_most_their_share_of_the_live_sessions` | hook |

## 4. Content

| Guardrail | Where | Test | Status |
|---|---|---|---|
| Studio, phone and agent go through one check: every job is queued by `JobManager.add`, which calls `moderation.refusal` (the phone uses the same `/api/jobs`, and `/api/jobs/{id}/retry`; a plan's step uses `studio.create_job`) | `jobs.JobManager.add` | `test_the_studio_and_the_phone_are_refused_the_same_words`, `test_a_plan_step_with_listed_words_is_refused_when_it_is_queued...` | live |
| The words a job draws on its result are checked too: motion scenes, cut cards, subtitles, a HyperFrames page's text, an ffmpeg command and its sidecars (before: the agent's film tools could draw refused words on a video) | `moderation.drawn_words` in `prompt_of` | `test_the_words_drawn_on_a_result_are_looked_at_too` | live |
| A plan with refused words is refused before it is priced and approved | `moderation.plan_problem`, hook in `plans.PlanRunner.create` | `test_a_plan_with_listed_words_is_refused_before_it_is_priced` | hook |
| Outside text reaches the model framed as data (`agent.external`): a web page, a text/PDF file, a transcript | `workspace` tools `web_fetch`, `read_text`, `transcript` | `test_a_web_page_...`, `test_a_text_or_pdf_file_...`, `test_a_transcript_..._read_in` | live |
| ...and when it is read back from memory (a transcript's lines, a file kept whole) | `guardrails.framed_state`; hooks: `runs.read` gives leaves' `writer`, `workspace.state_read` answers through it | `test_a_transcript_kept_in_memory_...`, `test_framed_state_...` | hook |
| ...and file names and a text's opening in the message (the attached items and the recent library items) | hook in `agent.question_parts` | `test_a_file_name_and_a_files_opening_reach_the_model_framed` | hook |

| **The content check**: one call to the fast model (`agent.helper()`, `claude.ask`, a structured answer) reads every plan's prompts and drawn words, in any language, before it is shown for Approve. It flags a real person's likeness the user gave no reference of, sexual content or anything involving minors, trademarks the user did not supply, copyrighted characters or a recreation of an existing film, game or show, and hate, harassment or violence beyond a film rating. `{flag: none/warn/block, categories, note}`: in mode **block** a `block` refuses the plan with a plain message; a `warn` (and in mode **warn**, the default, every flag) is one line on the plan card. Every flag is a row of `moderation` (kind `content_check`, the console's `GET /api/admin/moderation?show=checked`). The word list above is unchanged and still runs | `content_check.check`, called in `workspace._planning` before the plan is priced for Approve and in `plans.PlanRunner.create` (the same words' verdict is remembered, `SEEN`, so it is not asked twice) | `test_creative_director.py`: `test_a_flag_of_warn_is_a_note_...`, `test_a_block_refuses_the_plan_only_in_the_mode_that_blocks`, `test_the_check_fails_open_...` | live |
| **It fails open.** When the check's own call fails (Claude busy or down, an answer that can't be read), the plan goes on unchecked: the error is printed, kept for the console's Checks card ("Content check": a problem for an hour after it last failed), and the plan's activity says the check did not run. An outage of the model never stops the studio; the word list and the moderators' queue still apply | `content_check.check` (`except Exception`), `content_check.status`, `health.creative` | `test_the_check_fails_open_and_is_off_when_switched_off` | live |

Not moderated, by design: the agent's chat message itself (only what would be made is checked; the content check reads
the message only to judge the plan's words), and pictures.

## 5. Output checks

| Guardrail | Where | Test | Status |
|---|---|---|---|
| The answer is one JSON object, `reply` text, `steps` a list of objects; the rest is cleaned by `agent.shaped` (and Claude Code checks `output_format`'s JSON schema) | `guardrails.answer_problem` | `test_answer_problem_says_what_is_wrong_with_an_answer` | live |
| An answer that can't be read fails cleanly ("can't be read"), never loops | `agent._ask_claude_live` | `test_an_answer_that_cant_be_read_fails_cleanly` | live |
| ...after being sent back once (`MALFORMED_RETRIES`) with what was wrong | hook in `agent._ask_claude_live` | `test_an_answer_that_cant_be_read_is_asked_again_once` | hook |
| A finished plan with steps that can't run goes back at most `FIX_ROUNDS` = 2 times | `agent._ask_claude_live` | existing (`test_agent_shots`) | live |

## 6. Quality gates (hints, never blocks)

Before the user sees a plan, the studio reads its steps the way a creative director would and gives the model what it
finds, **once a message, as one hint, together with the big job's notes** (the concept, the stills first, the
automatic second opinion: [creative-director.md](creative-director.md)). The model decides what to change; a plan it
keeps is shown as it is. A gate judges only what a plan says (a shot with no `shot_size` is not called the same size as
another). Inside a long skill's run they run too, with the brief, concept and review fitted to the skill's stages
(`in_run`, [creative-director.md](creative-director.md)).

| Gate | What it sends back | Where | Test |
|---|---|---|---|
| Continuity | a place written two ways ("rainy night market" / "the night market in the rain"), or a person whose look (colours, hair, clothes) changes from shot to shot, unless a reference or an always-on NeuralCore character carries it | `guardrails.continuity_gate` | `test_the_continuity_gate_finds_a_place_or_a_person_written_two_ways` |
| Shot variety | a video plan of 3 shots or more all at one size | `guardrails.variety_gate` | `test_the_variety_gate_wants_more_than_one_shot_size` |
| The hook | a social video plan (portrait, or Reels / Shorts / TikTok / Stories in the message) of 2 shots or more that opens on a static wide with no hook | `guardrails.hook_gate` | `test_the_hook_gate_wants_a_social_video_to_open_on_a_hook` |
| No words from a video model | a video shot that asks for readable words (a sign that reads "OPEN", a title in big letters); spoken words are not text | `guardrails.video_text_gate` | `test_the_video_text_gate_finds_words_asked_of_a_video_model` |

They are gathered by `guardrails.quality_hints` and given by the `finishing` check in `api/workspace.py`
(`creative`); `test_the_quality_gates_are_one_hint_once_and_never_a_block` drives the route. The console's Checks card
lists them ("Quality gates") beside the content check.
