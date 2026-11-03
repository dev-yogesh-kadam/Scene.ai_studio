id: continuity-board
title: One scene in several clips, joined by a board of what was shown
version: 1
desc: Use when several clips must play as one unbroken scene and each clip is made on its own, its continuity carried by a numbered grid of stills from the clips so far, or the user asks for grid or board continuity, or which continuity method to use.
craft: true
words: \b(grid continuity|board continuity|continuity (board|grid|method)|staging grid|(one|same|unbroken|continuous) scene (in|across|over) (several|many|\d+) (clips|shots)|chain or board|board or (chain|recall))\b
---
It runs on three film operations: shots {"video"} (where a clip cuts), keyframes {"video", "count" or "times", or
"shots" with "pick": first, middle or last} (stills of a clip) and board {"stills": [{"video", "at"} or {"image"}],
"panels": 6, "numbered": true} (the grid). If the film tool refuses one of them, use Chain (below) and say so in one
line.

1. The method, once per film, kept at /continuity/method. Ask with "question" when the user has not said, the options
   "Chain (default)", "Board", "Recall":
   - Chain: each clip starts on the last frame of the clip before (a step with "after"). Smooth joins; redoing one clip
     means redoing every later clip of its scene, so say that before a retake.
   - Board (this skill): every clip is made on its own; a numbered grid of stills from the scene so far is its history
     and its highest panel the state it opens from. Any clip can be redone without touching the others.
   - Recall (continuity-recall): for people, places and props that come back after several clips; it can run beside
     Chain or Board.
2. The first clip of a scene is a normal step, with no grid.
3. After each clip that is kept (never a discarded take): take 2 or 3 stills that show how it unfolds, its final frame
   always among them (film keyframes on the clip with "count"; a clip of several shots: shots first, then keyframes
   with those "shots" and "pick" "last"), and number them on from the board's last number. Keep them at
   /continuity/board/<scene>/stills/<n> = {"item", "clip"}, n from 1 across the scene.
4. Build the board with film board from the newest stills in order, "panels" 6 and "numbered" true; with more than 6,
   pass only the newest 6 (the newest matter most). The board keeps itself between 0.4 and 2.5 times as wide as it is
   tall, so video models take it (16:9 stills 2 across and 3 down, 9:16 stills 3 across and 2 down); its numbers are
   its only text. Keep it at /continuity/board/<scene> = {"grid", "highest_panel"}.
5. Every later clip of the scene: put the grid in the workflow's extra reference slot (H3 Chunk: "Extra Reference")
   and write, before the shots: "The extra reference shows this scene so far as numbered panels in time order; the
   highest-numbered panel is the exact state this clip opens from; lower panels are history. Render none of its
   numbers, borders or tiling." Then the opening, read off the highest panel: where each person stands, their pose,
   facing and gaze, what they hold, the room and the camera direction. Give the clip a clear end state, since its last
   frame becomes the next highest panel. Character sheets and the place's picture still carry who and where.
6. Check each clip: it opens as the highest panel shows, and nothing of the grid shows in it (no numbers, no panel
   edges). A clip that fails is retaken from the same board.
7. A redone clip: replace its stills at their numbers, build the board again from the new list, and leave the later
   clips as they are.
8. A clip in a new place starts a new scene and a new board.
