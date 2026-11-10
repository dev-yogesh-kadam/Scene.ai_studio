id: model-limits
title: What image and video models do badly, and the workarounds
tags: limits, hands, fingers, text, words, letters, crowd, many people, fast action, physics, faces, consistency, logo, counting, workaround, honest, failure, failed, broken, breaking, garbled, melted, retake
when: Before promising a shot the models may not deliver; and after a shot fails twice.
---
# What image and video models do badly, and the workarounds

A creative director who knows the tools says early, in one line, when an idea will fight the model, and offers the
better way. That honesty is part of the craft: it saves the user's credits and gets a better film.

## The usual failures
| Weakness | What goes wrong | Workaround |
|---|---|---|
| **Hands doing fine work** | extra or fused fingers, impossible grips (typing, knitting, a guitar chord, opening a clasp) | frame the hands out or partly out; hands resting or holding simply; a wider shot where hands are small; cut to the result |
| **Readable words in video** | letters melt, misspell and shift between frames | words on screen as a designed page (render_html) over the clip; keep signs far off or soft; a picture (not video) can carry a few short words in quotes |
| **Many people interacting** | merged bodies, duplicated faces, crowds that melt | one or two people per shot; crowds soft in the background; singles and two-shots instead of a group shot |
| **Fast complex action** | blur, broken limbs, objects passing through each other (fights, sports, collisions) | split into simple shots: the wind-up, the reaction, the aftermath; slower motion; cut on the moment of contact |
| **Exact physical contact** | a kiss, a handshake, a hug, a pie in a face distort | a close two-shot just before, then a cut; silhouettes; shoot from behind one of them |
| **Same face across shots** | the character drifts between shots | a character reference in NeuralCore first; shots that start on an approved still; closer framings |
| **Counting and order** | "five candles" becomes seven; specific arrangements | fewer, larger objects; say "a few"; use a reference image |
| **Brand logos and labels** | invented, garbled marks | the user's own product photo as the start frame or reference; the logo on the end card as a page; never invent a logo |
| **Mirrors, reflections, glass** | wrong reflections, a second person in the mirror | avoid mirrors in frame, or make the reflection the shot |
| **Long continuous takes** | the scene drifts after 8–10 s | shorter shots chained (`after`), or the chain workflow with several clips |
| **Complex camera choreography** | a move that changes mid-shot wobbles | one move per shot (see `camera-moves`) |
| **Small text-heavy UI** | phone screens and apps come out as gibberish | a blank glowing screen; the real UI composited later; a designed page |
| **Animals' anatomy in motion** | extra legs on a running horse or dog | medium or slow movement, a side view, or a close-up of the face |

## How to say it
- One line, plain, with the better way: "Readable words inside the video will come out garbled, so I'll put
  'Open till midnight' on a designed end card instead."
- Say it before the plan, not after the user has paid for the failure.
- Offer the alternative in the plan itself; ask only if the alternative changes what the user sees a lot.

## When a shot fails twice
- Stop rewording the same prompt: change the approach (framing, number of people, a reference, another workflow).
- Say plainly what the model cannot do and offer the other ways as a question card.

## What the models do well (lean on it)
- Light, atmosphere, weather, texture, materials, food, landscapes and architecture.
- One person doing one clear action at medium or close range.
- Slow, steady camera moves; static frames with motion inside them.
- Mood and colour, when you name them.

## Ethics, briefly
- No real person's likeness without the user's own reference (and their right to use it).
- No recreation of a specific film, show, game or character: learn the grammar, make something original.
- Never present invented facts, quotes or testimonials as real.

See also: `character-consistency`, `product-shots`, `type-and-motion`, `prompters/` for each model's own guide.
