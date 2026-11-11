# The creative rubric

How the studio measures taste. Six marks, each 1 to 5 (2 and 4 lie between the descriptions). The same rubric is used
by the Opus judge of the creative evals (`backend/evals/creative.py`, live mode), by the fast model's grade of a share
of real turns in Langfuse (`Agent.grade`, the scores `creative-idea` … `creative-honesty`), and by you when you
calibrate the judge (`python -m evals.calibrate`). Its text for the models is `agent.CREATIVE_RUBRIC`; change both
together.

A turn that rightly asked a question instead of planning (a big job's brief, directions for an open brief) is judged on
the question: **idea** and **fit** by whether its options lead to a strong, well-aimed piece, the rest at 3.

| Mark | 1 | 3 | 5 |
|---|---|---|---|
| **idea**: one clear concept | No idea: a list of shots, or the brief repeated back. | An idea is there, but generic ("a nice cafe ad") or blurred between two. | One clear concept, sayable in one sentence, that every shot serves ("a rainy-night chase that ends at the warmest table in town"). |
| **hook**: the opening grabs | Opens slowly: an empty establishing wide, a logo, a title card, three seconds of nothing. | A decent opening a scroller might still pass: some motion, but no reason to stop. | The first one or two seconds stop the scroll: motion already under way, a face close to camera, a surprise, the product at its most striking. Strictest for social video. |
| **craft**: shot variety, camera, light, continuity | Every shot the same size and angle, moves with no motive, no light named, people and places described differently from shot to shot. | Some variety and continuity, light named here and there, one or two moves with a reason. | Coverage that moves with the story (wide, medium, close, insert), motivated camera, light and colour that serve the mood, the same people and places written word for word, screen direction kept. |
| **fit**: audience, platform, shape | The wrong shape or length for where it runs, the wrong language, the audience ignored. | The right shape and length, but generic for the audience. | Shape, length, tone, language and the call to action made for this audience on this platform (and the safe areas kept). |
| **prompt quality**: concrete, model-appropriate | Vague prompts ("a cool shot of a cafe"), settings written into the prompt, one prompt doing three actions. | Concrete subject and action, but missing the camera, the light or the model's own prompt structure. | Concrete, complete prompts in the model's own structure and length, one action a shot, asking nothing the model does badly. |
| **honesty**: no overpromising, flags model limits | Promises what the models cannot do (readable words in a video, a crowd interacting, fine hand work, a celebrity) or invents claims and facts. | Avoids the worst failures but says nothing of the limits it steered around. | Says plainly, in one line, what will not work and plans the better way (a designed title card, fewer people, a reference first); invents no facts, claims or likenesses. |

## Thresholds

A creative eval case passes when every mark is at least **3** (`evals/creative.py`, `THRESHOLD`). A case may ask for more
on the marks it is about: `"expect": {"creative": {"hook": 4}}`.

## Calibrating

The judge is a model and may be too kind or too strict. Run `python -m evals.calibrate` on a few cases now and then:
you see each plan and the judge's marks and give your own; `backend/evals/calibration.json` keeps them, and the report
says per mark how far the judge is from you on average and which way it leans. A mark where it stays more than 1 apart
needs its rubric line rewritten (here and in `agent.CREATIVE_RUBRIC`), or the threshold moved.
