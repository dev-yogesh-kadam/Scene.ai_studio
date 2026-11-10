id: camera-moves
title: Camera moves and what they mean
tags: camera, move, push in, pull back, pan, track, dolly, crane, handheld, orbit, static, motivated, whip, drone
when: Choosing a move for a video shot: every move needs a motive.
---
# Camera moves and what they mean

A camera move is a sentence the audience feels before they understand it. A move with a motive deepens the shot; a
move without one is decoration, and with AI video it is also one more thing that can wobble. When in doubt, hold
still: a locked frame with strong action is often the stronger shot.

## The moves (studio values for `move`)
| Move | What it says | Motive to use it | Watch for |
|---|---|---|---|
| **static** | observe; let the action speak | performance, product hero, comedy timing | needs action inside the frame |
| **push in** | realisation, focus, intimacy, dread | the moment a character understands; a product reveal | slow is emotional, fast is shock |
| **pull back** | isolation, scale, revelation of context | an ending; "she is alone"; showing the whole place | ends on a wide that must be worth it |
| **pan** | look around; follow a gaze; connect two things | from a face to what it sees | fast pans blur; keep them slow |
| **track** (dolly/truck) | go with someone; energy; journey | walking-and-talking, a run, a product line-up | keep the subject's size steady |
| **crane** | grandeur, arrival, transition between levels | an opening over a market; rising over a crowd at the end | needs a big place |
| **handheld** | urgency, panic, documentary truth | a chase, an argument, a real-life testimonial | subtle shake, not chaos |
| **orbit** | a moment held in time; the hero; the product | a reveal, a product turning, a kiss | slow; one orbit is plenty |

## Motivation, in practice
- **Move with the subject:** the camera tracks because she runs.
- **Move toward meaning:** the push-in lands on the face at the line that matters.
- **Move to reveal:** the pull-back shows the empty chair she didn't see.
- **Move with the music:** a slow rise over a building chorus; a snap cut on the drop.
If you cannot say the motive in five words, choose static.

## Speed and length
- Slow (over 5–8 s): emotional, cinematic, luxurious.
- Medium (3–5 s): narrative, natural.
- Fast (under 2 s, a whip or a snap zoom): energy, comedy, transitions. AI video handles fast moves badly; prefer a cut.
- One move per shot. A push-in that becomes a pan that becomes an orbit is three shots.

## By genre and format
- **Ads and product:** slow push-ins and orbits on the product; static for the demo; one crane for a place.
- **Social:** handheld or a fast track for the hook, then simple moves; the energy comes from cutting.
- **Drama:** mostly static and slow push-ins; save the move for the turn.
- **Horror:** slow push toward a doorway; static wides that let the eye search; no shake until the scare.
- **Action:** tracking and handheld, but keep the geography readable (see `screen-direction`).
- **Documentary:** handheld, observational, eye level, reframing as life happens.

## In the studio
- Set `move` on every scene step and describe how it ends in `end_state` ("the camera settles on her hands").
- For a model whose guide times the shot beat by beat, the camera goes in its beats; the studio does not add it twice.
- Chained shots: end a move where the next shot can begin (a push-in that ends close lets the next shot start close).
- Presets (`preset_search`, category camera moves) hold tested words for each move: paste them.

## Traps
- An orbit around a person talking (it wobbles and distracts).
- A drone crane over every opening.
- Handheld on a calm product shot.
- A move that ends on nothing.

See also: `shot-grammar`, `pacing`, `scene_presets/` for each kind of scene's camera and cutting.
