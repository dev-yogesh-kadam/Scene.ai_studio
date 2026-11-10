id: social-hooks
title: Hooks for social video (Reels, Shorts, TikTok)
tags: hook, social, reels, shorts, tiktok, stories, portrait, opening, retention, scroll
when: Any vertical social video, or any piece whose first seconds decide whether it is watched.
---
# Hooks for social video

The feed decides in about a second. The viewer is scrolling, the sound is often off, and the thumb is faster than your
story. A hook is not a trick added on top: it is the first image of the idea, chosen so that stopping is easier than
scrolling.

## The rule of the first 1–2 seconds
- **Motion before meaning.** Something must already be moving in frame 1: a hand, a pour, a run, a camera push. A still
  wide establishing shot is the classic hook-killer.
- **A face close to camera.** Eyes in the upper third, looking at or just past the lens. A face reads faster than any
  object, and an expression (surprise, a held laugh, worry) is a question the viewer wants answered.
- **The product at its most striking,** not its most complete: the crack of the crust, the drip, the steam, the glint,
  macro close. Show the moment of desire, not the packshot.
- **An open loop.** Start in the middle ("…and that's when the cat stole the croissant"), on a before that promises an
  after, or on something slightly wrong (a cup filled to the brim, a door left open in the rain).
- **Never open on a logo, a title card or an empty room.** Brand at the end, or as a small mark; the opening is earned
  attention, not owned.

## Hook patterns that work
| Pattern | What frame 1 shows | Good for |
|---|---|---|
| Reveal | a close detail that becomes the whole on a pull-back | product, food, place |
| Action-in-progress | the peak of a movement, mid-air, mid-pour | sport, food, energy |
| Face + reaction | a person reacting to something we can't see yet | testimonial, comedy, drama |
| Before → after | the "before" with an obvious promise of change | beauty, home, fitness, service |
| Pattern break | something visually odd or out of place | brand, comedy |
| POV | the viewer's own hands, their view | apps, food, travel, unboxing |
| Question on screen | 3–6 words of type over a striking first frame | explainer, tips (type as a page, not inside the video) |

## Building it in the studio
- Make the hook its own shot: 2–4 s, MCU or CU, a move with a motive (push in, handheld follow, a fast track). The
  model gives its best motion when one clear action fills the frame.
- Put the hook **first in the plan**, shot_number 1, and let the rest of the piece pay it off.
- Words on screen ("Wait for it", "3 cafe tricks") go as a designed page over the clip (render_html), never as text the
  video model draws: models garble letters.
- Sound-off first: the hook must work in silence; music and voice add to it, never carry it alone.
- Portrait 9:16, the subject inside the middle 4:5 so the platform's buttons and captions don't cover it (see
  `platform-specs`).

## After the hook
- **Second 2–5 is the promise:** say (or show) what the viewer gets for staying. A recipe shows the dish, a story shows
  the stakes.
- **Keep a change every 1.5–3 s** in a fast reel: a cut, a new size, a move. Long holds are for weight, not for filler.
- **Pay it off before the end.** A hook that is never answered loses trust; the loop you opened in frame 1 closes by
  the last beat.
- **End on the action you want:** the shop's door, the product in a hand, the line "Open till midnight" as a card. A
  loopable last frame (it cuts cleanly back to the first) earns replays.

## Traps
- A slow drone wide over a city as frame 1.
- Three seconds of a logo animation before anything happens.
- A hook that promises something the piece never delivers.
- Text the video model is asked to render ("a neon sign that says SALE" inside the clip): it will be misspelt.

See also: `skills/social-video.md` (the studio's social skill), `scene_presets/reveal.md`, `pacing`, `platform-specs`.
