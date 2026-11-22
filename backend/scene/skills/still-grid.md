id: still-grid
title: Still Grid
version: 2
desc: Keeps a multi-clip scene continuous using a grid of earlier stills
description: Use when several clips must play as one unbroken scene but each clip should be generated on its own, with continuity carried by a numbered grid of stills from the scene so far, or the user asks for "still grid". Building block: works inside any workflow and for any video model. Never triggers on its own: load only when the user or another skill explicitly calls for it.
craft: true
words: \b(still grid|grid continuity|board continuity|continuity (board|grid|method)|staging grid|(one|same|unbroken|continuous) scene (in|across|over) (several|many|\d+) (clips|shots)|chain or board|board or (chain|recall))\b
---
# Continuity Board

Every clip is a normal generation. What ties them together is one image: a numbered grid of stills from the clips made so far. The model reads it as the scene's history, and the highest panel as the state to start from. Any clip can be redone without breaking the others.

**Studio:** the stills come from the film tool's keyframes (a clip of several shots: shots first, then keyframes with those "shots" and "pick" "last"; else "count"), and the grid from its board {"stills": [...], "panels": 6, "numbered": true}, which numbers, tiles and keeps the 0.4–2.5 shape itself: those are the ffmpeg_job and the ffmpeg-recipes here. The grid goes in the video model's numbered reference pictures, after the anchor and the sheets (its last @Image).

## First clip of a scene
A normal generation, with no grid.

## Every clip after it
Save at `/continuity/clips/<n>` (n: the clip number the inputs give):
- `mode`: `generate`.
- `grid`: the scene's grid and its highest panel number.
- `opening`: the state in the highest panel, written out: where each subject stands, their pose and facing, prop states, the space and the camera direction.
- `end_state`: a clear final state, since it becomes the next highest panel.

## Building the grid
After each kept clip (never a discarded take):
- Take a few stills that show how the clip unfolds, always including its final frame.
- Number them in order, continuing from the grid's last number.
- Add them to the grid so it reads left to right, top to bottom.
- Keep it clean: the numbers are the only text, with no borders or captions.
- Keep 6 panels at most. Past that, drop the oldest; the newest panels matter most.
- Lay it out by the stills' shape so the whole grid stays between 0.4 and 2.5 times as wide as tall (video models reject other shapes): 16:9 stills in 2 columns × 3 rows, 9:16 stills in 3 columns × 2 rows, 1:1 either way.
- Save it at `/continuity/board/<scene>`: grid, highest_panel.

Use `ffmpeg_job` for numbering and tiling (see **ffmpeg-recipes**).

## Checks
- The clip's opening matches the highest panel.
- Nothing from the grid shows up in the video: no numbers, no panel edges.

## Changing a clip
Regenerate it, replace its stills in the grid, and renumber. Later clips keep their renders.
