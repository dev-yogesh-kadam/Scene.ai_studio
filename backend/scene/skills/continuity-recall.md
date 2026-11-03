id: continuity-recall
title: Keeping people, places and props the same when they come back
version: 2
desc: Use when a film of many shots has people, places or props that come back after several shots, or the user asks for smart referencing or continuity.
craft: true
words: \b(continuity|smart referenc\w*|keep (her|him|them|it) the same|looks? different (now|again)|consistent (across|between)|same (face|outfit|place) (as|in) (before|shot))\b
---
A memory of what the film has already shown: every kept clip leaves one labelled keyframe per shot, and before each
new clip the few it needs are picked and given to the model as one numbered grid. It works alone or beside Chain or
Board (continuity-board). Who someone is still comes from NeuralCore; the grid shows how things looked on screen.

1. Identity first. Read /cast for everyone and everything in the next clip. A person or place that changed has a look
   of its own ("maya_torn_sleeve" with "look_of" maya, "from_scene" 3; "kitchen_night" with "variant" night): use the
   look the scene calls for, and the base entry everywhere else. A location's "palette" goes into the prompt word for
   word. Make a look entry ("Maya - torn sleeve") the first time a change shows on screen and recurs.
2. Every shot made keeps its record: give each step "save_to": "/videos/<n>". When a clip is kept (never a discarded
   take), save its keyframes:
   - a clip of several shots: film shots {"video", "save_to": "/continuity/recall/shots/c<n>", "run"} for its cuts;
   - film keyframes {"video", "shots": the spans found (or [[0, its length]] for one shot), "pick": "middle",
     "labels": one per shot, "save_to": "/continuity/recall/keyframes/c<n>", "run"}. Each shot's frame is kept at
     .../c<n>/<shot>/keyframe and a copy with its label in a strip below the picture at .../c<n>/<shot>/keyframe_captioned.
   - The label says what is in it, with no clip or shot numbers, from the plan and checked with look:
     "Maya and Ravi, kitchen, wide from the door, evening, Maya's sleeve torn". Write it at .../c<n>/<shot>/label.
3. Picking for the next clip:
   - List what it needs: who appears, where, which props, in what state, from what angle.
   - state_read /continuity/recall/keyframes and match each need to a label: the subject first, then the state and
     angle, then the most recent.
   - Take only what the sheets and the location's picture don't already give: how a place was lit and framed, a
     costume or prop that changed on screen, where people stood. One pick per need, 6 at most.
4. The grid: film board {"stills": [{"image": each pick's keyframe_captioned item}], "panels": 6, "numbered": true}, in
   the order the clip uses them (the first shot's needs first). Keep it at /continuity/clips/<n>/grid, with
   /continuity/clips/<n>/panel_lines: one line per panel saying what to take from it.
5. In the clip's step, put the grid in the workflow's extra reference slot (H3 Chunk: "Extra Reference") and write the
   panel lines into the prompt before the shots: "The extra reference holds numbered panels in shot order, read left
   to right, top to bottom. Panel 1 is the kitchen as seen earlier: use only its layout and light for shot 1. Panel 2
   is Maya's torn sleeve: keep it in shots 2 and 3. Render none of its numbers, captions or panel edges." Never use
   a keyframe as the character's identity reference: rendered frames drift clip after clip.
6. After the clip is made and checked, save its keyframes (step 2) before the next clip is planned.
7. When a review says someone looks different, retake with their NeuralCore entry (or look) as the reference and the
   label's words in the prompt; after two failures, offer to make a new character sheet for NeuralCore instead.
