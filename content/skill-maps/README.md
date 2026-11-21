# Skill maps

Moved here from `documentation/` on 10 November 2026; the craft skills the pages describe are now in `content/craft-skills/v1` (was `craft skills/`) and `content/craft-skills/v2` (was `craft skills v2/`). The pages keep the old folder names as they were written.

Reference pages about how the studio works, kept for anyone joining later. Each `.html` file opens on its own in a
browser (double-click it); nothing else is needed.

| Page | What it shows | Online copy |
|---|---|---|
| [studio-skills-map.html](studio-skills-map.html) | The studio's own skills (`backend/scene/skills/`): what you type and which skill answers, the script-to-video flow step by step with the workflow each step runs on, the helper skills and who calls them, and when to pick Chain, Board or Recall continuity. | https://claude.ai/artifact/VUaosscwQcAAdmtvP9VUfu |
| [craft-skills-v2-review.html](craft-skills-v2-review.html) | The review of `craft skills v2/` (3 November 2026): every file compared with v1 and with the studio, what changed skill by skill (3 new skills, 2 rewritten, 23 scene recipes), what helps us most, the craft tools mapped to studio tools, what the studio is missing, our prompting compared with craft v2's, and the 16 decisions (all answered as recommended on 4 November, when v2 was ported; its Status section says what was done and what is still missing). | https://claude.ai/artifact/YRLnXHNBYKecSiCuKHLWUR |
| [craft-v2-prompting-review.html](craft-v2-prompting-review.html) | Craft v2's prompting compared with the studio's (4 November 2026), workflow by workflow for all 6 picture and 11 video workflows: who covers what, v2's sheet, location, anchor and shot-frame templates on each picture model (references, word limits, negatives), the H3 prompter against our `minimax-h3` guide rule by rule and slot by slot, the other video workflows, what to borrow from the Seedance and Wan 3 prompters, our own prompting gaps, and decisions P1–P9. | https://claude.ai/artifact/2DxoDpRsSgGj7uwhC46eBB |
| [craft-skills-map.html](craft-skills-map.html) | How the 24 skills in `craft skills/` connect as one system: a connection map (who loads whom, who hands data to whom, which guides are missing), what passes along each link, each skill's links in and out, the run order, which continuity skill and prompter run when, which scene presets mix with which, the loose ends found, and where each one is now in the studio. | https://claude.ai/artifact/BrCDmE56rR24FoMVm8KqRA |

The online copies are private claude.ai pages: they open only for the account they were published from
and anyone it shares them with.

## Related notes elsewhere in the repo

- `docs/craft-gaps.md`: what the craft skills needed from the studio, what was built, and what still waits on Zoro.
- `docs/zoro-agent-prompt.md`: the install brief given to the agent on Zoro (the render PC).
- `docs/zoro-downloads.md`: the models to download on Zoro.

## Keeping these up to date

Both maps describe the skills as they were on 3 November 2026, before craft skills v2 was ported on 4 November (script-to-video's 8 steps, the new script-writer, anchor and H3 prompter skills, Board as H3's default continuity): `studio-skills-map.html` is out of date until it is redrawn. When a skill is added, removed or changes what it
calls, update the page: the skill files themselves are the truth (`backend/scene/skills/*.md`, `craft skills/`).
