id: wan
title: Wan
workflows: ^video/(video_v2v_wan|video_outpaint_wan|video_wan_)
length: 60 to 120 words
limit: 250
---
Wan's text encoder (umT5) reads plain prose best and loses the end of a long prompt: keep to the length and put the
most important first. Short sentences, no labelled blocks, no timecodes, no dialogue. In this order:
subject (who or what, how they look) → scene (where, what is around) → motion (what moves and how) → camera (one move,
in film words) → look (light, colour, style, lens feel).

By workflow:
- Restyle (Wan VACE, Wan 2.2 Fun Control): the motion and camera come from the video. Describe the new look: the
  people and things as they should now appear, the place, the light, the style. Never a different action.
- Outpaint: describe what lies around the frame as a still place: the room, the street, the sky, the floor. Nothing
  new that moves, no new people.
- Animate: the character comes from its picture and the motion from the driving video. Describe the background, the
  light that falls on the character, and the camera; not the character's look or its moves.
