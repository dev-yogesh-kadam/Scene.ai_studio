id: continuity-chain
title: One scene in several clips, each carrying on from the clip before
version: 1
desc: Use when several clips must play as one unbroken scene and each clip should carry straight on from the one before it, or the user asks for chain or v2v continuity.
craft: true
words: \b(chain continuity|v2v continuity|carry (it )?on from (the )?(last|previous) (clip|shot)|continue (from|where) (the )?(last|previous) (clip|shot))\b
---
Every clip after the first starts where the one before it stopped, so the place, the people and the light carry over.
The studio does it from the earlier clip's last frame today; a true extension from the clip itself (motion and sound
carried over) waits for the Zoro workflow video_extend_wan_vace to be connected: until the workflows list it, use the
last frame and say so once.

1. The first clip of a scene is a normal step.
2. Every clip after it: a step with "after" the clip before (it starts on that clip's last frame). Before writing its
   prompt, look at the last seconds of the kept clip: that boundary is ground truth. Write its opening from them: each
   person's posture, facing and gaze, where the props are, the space, the camera's position and framing, the light,
   the sound, and any motion still under way. Keep at /continuity/clips/<n>: {"mode": "after", "source": the clip,
   "opening", "locks", "end_state"}.
3. Locks, in the prompt: every person stays one continuous person (no duplicates, no splitting), with the same face,
   clothes, props, layout, camera axis and ambience; the clip continues the action from its first frame, no pause, no
   fade.
4. Give each clip a clear end state: the next one starts from it.
5. Carry on only from the take the user kept. Redoing one clip takes away the starting point of every later clip of
   its scene: say so and ask before a retake, then remake those after it in order.
6. A change of place or time starts a new scene with a normal step, not a chain.
