id: screen-direction
title: Screen direction and continuity
tags: continuity, screen direction, 180 degree rule, eyeline, match cut, axis, consistency, wardrobe, props, time of day, chaining
when: Any sequence of shots of the same people or place: keep the viewer oriented across cuts.
---
# Screen direction and continuity

Continuity is what lets the viewer forget there are cuts. Break it by accident and they feel lost without knowing why;
break it on purpose and it becomes a jolt you control.

## The axis (the 180° rule)
- Draw an imaginary line through the two people in a conversation, or along a person's path. Keep the camera on one
  side of it for the whole scene.
- Then **A looks right, B looks left** in every shot, and a runner going **left to right** keeps going left to right.
- To cross the line, show the crossing: the camera moves across in one shot, the person turns in frame, or a neutral
  shot (straight on, or straight from behind) resets the axis.
- In a chase, the pursuer and the pursued move the same way across the screen; a reversal reads as "they turned back".

## Eyelines
- When someone looks off-screen, the next shot shows what they see from the side they looked. A look up-left is
  answered by something up-right in the reverse.
- Two people talking: their eyelines meet; each looks slightly off the lens toward where the other stands.

## What must match from shot to shot
| Thing | Studio tool |
|---|---|
| The face | a NeuralCore character entry in a character slot; or the same few words, word for word |
| Clothes and hair | the same description word for word, or an outfit entry; never "a jacket" then "a coat" |
| Props in hand | named in every shot that shows them, in the same hand |
| Place | `place` written the same way in every shot there ("rainy night market") |
| Time of day and light | the same light sentence in every shot of the scene |
| Weather | rain stays rain; wet ground stays wet |
| Direction of travel | the move and end_state describe the same direction |

## Chaining in the studio
- A shot in the same place as the one before starts on its last frame automatically, and is checked against it:
  continuity for free. Use `after` to chain within a plan.
- To start fresh in the same place (a new day, a jump in time), name the place differently ("Meera's kitchen, next
  morning").
- `end_state` is a promise to the next shot: "she reaches the door, hand on the handle" → the next shot opens with her
  hand on the handle.
- For long pieces keep a continuity board of the stills (`skills/continuity-board.md`) and recall the right reference
  for each shot (`skills/continuity-recall.md`, `skills/continuity-chain.md`).

## Matching cuts on purpose
- **Match on action:** cut in the middle of a movement (a hand reaching, a door swinging); the motion hides the cut.
- **Graphic match:** a shape or colour carries across (the ring of a cup → the full moon).
- **Sound bridge:** the next scene's sound starts under the last shot of this one.

## Breaking it on purpose
- A jump cut (same framing, time skipped) for impatience, a montage of waiting, social-video energy.
- A crossed axis for disorientation in a fight or a nightmare — once, and only if the scene is about losing control.

## Traps
- Describing the heroine differently in shot 3 ("a young woman") from shot 1 ("a girl of about twenty with a braid").
- A runner going right in shot 1 and left in shot 2 with no turn.
- Day in the wide, golden hour in the close-up.
- A new location name for the same place, which breaks the studio's chaining.

See also: `character-consistency`, `shot-grammar`, `scene_presets/chase.md`, `scene_presets/conversation.md`.
