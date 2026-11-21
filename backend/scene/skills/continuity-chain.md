id: continuity-chain
title: Craft Continuity Chain
version: 2
desc: Keeps a multi-clip scene continuous by extending each previous clip
description: Use when several clips must play as one unbroken scene and each clip should be a forward extension of the clip before it, or the user asks for "v2v continuity". Craft skill: works inside any workflow. Never triggers on its own: load only when the user or another skill explicitly calls for it.
craft: true
words: \b(chain continuity|v2v continuity|carry (it )?on from (the )?(last|previous) (clip|shot)|continue (from|where) (the )?(last|previous) (clip|shot))\b
---
# Continuity Chain

Every clip after the first is a forward extension of the one before it. The model sees the earlier clip and starts the new one where it stopped, so motion, space and sound carry over on their own.

**Studio:** Chain is offered on the video models script-to-video's table gives it (Seedance 2.5 and Wan 3: their Reference video slot, cited as @Video1). A clip after the first is a "generate" step with the kept clip before in that slot ("uses"); `mode: extend`, `source_video` and `role: extend` are that slot. A clip before that is too long for the slot is trimmed first, as the prompter's §5 says (Seedance 2.5: its last 29 s; Wan 3: its last 15 s), with the ffmpeg tool, keeping its end; the studio refuses a step whose reference video is over the model's seconds and says so. On a model without Chain (Seedance 2.0, MiniMax H3), when the user asks for Chain anyway, the clip is a "generate" step with "after" the clip before: it starts on that clip's last frame, so motion and sound do not carry over, and faces can drift; say so once.

## First clip of a scene
A normal generation: mode `generate`.

## Every clip after it
Save at `/continuity/clips/<n>` (n: the clip number the inputs give):
- `mode`: `extend`, `direction`: forward, `source_video`: the clip before, `role: extend`.
- `opening`: what must hold across the boundary, read off the source's final frame: each subject's posture and facing, where the props are, the space, camera position and framing, lighting, the sound, and any motion still in progress.
- `locks`: every subject stays one continuous instance (no duplicates, no splitting), with the same face, clothing, props, layout, camera axis and ambience.
- `end_state`: a clear final state, since the next extension starts from it.

## Between clips
Watch the last seconds of the kept clip before writing the next `opening`; that boundary is ground truth. **Studio:** look "deep" at the clip, or film keyframes of its last seconds. Extend only from the clip the user kept.

## Changing a clip
Each extension starts from the clip before it. Replace one and every later clip in that scene loses its starting point and needs regenerating. Tell the user before changing it.
