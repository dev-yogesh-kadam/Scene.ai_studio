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

**Studio:** no workflow here extends a clip yet (`video_extend_wan_vace` is not connected), so script-to-video does not offer Chain on H3. When the user asks for it anyway, a clip after the first is a "generate" step with "after" the clip before: it starts on that clip's last frame, so motion and sound do not carry over, and faces can drift; say so once. `mode: extend`, `source_video` and `role: extend` are that "after".

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
