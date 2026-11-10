id: type-and-motion
title: Typography and motion-graphics principles
tags: typography, type, font, motion graphics, kinetic type, titles, lower third, end card, layout, hierarchy, animation, easing, hyperframes, logo
when: Words on screen, title cards, end cards, lower thirds or any motion-graphics piece.
---
# Typography and motion-graphics principles

Words on screen are read on a phone, in a second, often with no sound. Design for that: few words, big, clear, with
one idea at a time. In the studio, words on screen are pages you design (render_html, HyperFrames), never words a video
model draws.

## Type
- **Two typefaces at most:** one for headlines (character, weight), one for text (readable). Or one family in two
  weights.
- **Hierarchy:** one thing biggest. Size, weight, colour and position say what to read first.
- **Size on a phone:** headlines at least about 6–8% of the frame height; body text no smaller than about 3.5%.
- **Few words:** a headline up to 6 words, a line up to 12; a frame that must be read in 2 seconds has under 8 words.
- **Contrast:** light on dark or dark on light; on video, add a soft shade, a box or a blur behind the type.
- **Line length and spacing:** short lines, generous line spacing, a little tracking on capitals.
- **Language:** set Hindi in a Devanagari face (Noto Sans Devanagari, Mukta, Hind) — never a Latin face that lacks
  the glyphs; Spanish needs its accents (á, é, ñ). Use the user's exact words.

## Layout
- A grid: margins at least 5–8% of the frame; type inside the safe area (see `platform-specs`).
- Align to edges or a centre axis; do not scatter.
- White space is part of the design; crowded frames read as cheap.
- One focal point per frame; a picture or clip behind type is darkened or blurred where the type sits.

## Motion
- **Every move has a job:** reveal, emphasise, connect, transition. No motion for its own sake.
- **Easing:** ease-out for things arriving (fast, then settle), ease-in for things leaving; never linear for UI or
  type. A small overshoot feels alive; a big one feels cheap.
- **Timing:** type in over 0.3–0.6 s, held long enough to read twice (about 0.3 s a word plus a second), out faster
  than in.
- **Stagger:** words or lines in one after another, 60–120 ms apart.
- **Consistency:** one motion language (the same easing, direction and duration family) through the piece.
- **Rhythm:** hits on the music's beats (see `pacing`).

## Pieces
- **Title card:** the name, one line under it, held 2–3 s; motion that suits the tone (a slow fade for drama, a
  kinetic snap for social).
- **Lower third:** name and role, left-aligned in the lower third, inside the safe area, 3–5 s.
- **End card:** logo, one line, the call to action (address, handle, "Order now"), 2–4 s, the brand's colours.
- **Kinetic type:** each phrase a beat; big words for the stressed ones; cut or move on the rhythm of the voice or the
  music.
- **Explainer:** one idea per scene, an icon or a number with each, a consistent palette and grid.
- **Logo reveal:** build it from its own shapes; prepare the logo first with the film tool's `logo` op; never redraw a
  brand's mark.

## In the studio
- Single pages: render_html with the html-scenes skill. Brand motion and projects: brand-motion and hyperframes skills.
- Look at the review sheets and the phone view before showing the user.

## Traps
- A paragraph on screen.
- Five fonts and three alignments.
- Type over a busy picture with no contrast.
- Type asked of a video model ("a sign that reads OPEN 24 HOURS" in a clip).

See also: `skills/html-scenes.md`, `skills/motion-graphics.md`, `skills/brand-motion.md`, `skills/hyperframes.md`.
