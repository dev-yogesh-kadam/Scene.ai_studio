---
name: continuity-chain
label: Continuity Chain
description: "Use when several clips must play as one unbroken scene and each clip should be a forward extension of the clip before it, or the user asks for \"v2v continuity\". Craft skill: works inside any workflow."
command: false
---

# Continuity Chain

Every clip after the first is a forward extension of the one before it. The model sees the earlier clip and starts the new one where it stopped, so motion, space and sound carry over on their own.

## First clip of a scene
A normal generation: mode `generate`.

## Every clip after it
Save at `/continuity/clips/<n>` (n: the clip number the inputs give):
- `mode`: `extend`, `direction`: forward, `source_video`: the clip before, `role: extend`.
- `opening`: what must hold across the boundary, read off the source's final frame: each subject's posture and facing, where the props are, the space, camera position and framing, lighting, the sound, and any motion still in progress.
- `locks`: every subject stays one continuous instance (no duplicates, no splitting), with the same face, clothing, props, layout, camera axis and ambience.
- `end_state`: a clear final state, since the next extension starts from it.

## Between clips
Watch the last seconds of the kept clip before writing the next `opening`; that boundary is ground truth. Extend only from the clip the user kept.

## Changing a clip
Each extension starts from the clip before it. Replace one and every later clip in that scene loses its starting point and needs regenerating. Tell the user before changing it.
