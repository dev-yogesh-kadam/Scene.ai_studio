id: character-consistency
title: Character design consistency
tags: character, consistency, face, identity, reference, character sheet, outfit, mascot, cast, same person, neuralcore
when: Any piece where the same person, mascot or creature appears in more than one shot.
---
# Character design consistency

A viewer forgives a lot, but not a face that changes. With AI models the same words do not give the same face twice;
consistency is something you build: a reference, a fixed description, and a plan that protects both.

## Design the character before the shots
- **Silhouette:** recognisable in shadow (a long coat, a braid, a hat, a posture).
- **Three anchors:** one face feature (freckles, a scar, thick eyebrows), one hair feature (a high bun, silver streak),
  one wardrobe signature (a yellow raincoat, a red scarf). These are the details the eye checks.
- **Palette:** two or three colours for the character, distinct from the background palette.
- **Age, build, skin, ethnicity, clothes** in plain concrete words. Avoid celebrity likenesses: the user's own
  reference, or an invented person.

## Lock the character
1. **Make the reference first:** a clean, neutral, front-lit picture of the character (a character sheet: front,
   three-quarter, profile; see `skills/character-sheet.md` and `skills/asset-designer.md`).
2. **Keep it in NeuralCore** with `keep` {"as": "character", "name": "Maya"}: every later shot puts it in the
   workflow's character slot.
3. **Approve it before shots.** A reference that came out wrong makes every shot wrong; remake it first.
4. **Write the same fixed description** in every prompt when there is no reference — word for word, never paraphrased.

## In every shot
- With a reference in the slot: call the character by what they are ("the girl", "the old fisherman"), do not
  re-describe the face (the reference carries it); do describe what changes (the action, the expression, wet hair).
- Keep the outfit the same unless the story changes it (and then keep an outfit entry for the new look).
- Mid shots and close-ups hold identity best; tiny figures in a wide lose it (fine for a wide, but the close-up
  must match).
- One character per reference slot; for two people, two slots, and tell the prompt which is which.

## Mascots and stylised characters
- Fix the style in words and a style reference ("flat 2D vector, thick black outline, three colours").
- Simple shapes stay consistent; intricate patterns and accessories drift — fewer details, bolder.
- Same proportions across shots (head-to-body ratio) and the same colour values.

## Several characters
- Make each distinct at a glance: different silhouettes, colours and heights.
- Wide shots with many people are hard for the models (see `model-limits`): cover a group with singles and two-shots.

## Checking
- The studio's review compares faces with the reference ("who"). A failed face is retaken with the reference, not with
  more words. When the same face fails twice, change the approach: closer framing, a shot that starts on an approved
  still, or the anchor workflow.
- Continuity tools for long pieces: `skills/anchor.md`, `skills/continuity-recall.md`.

## Traps
- "A beautiful woman" in shot 1, "a young lady" in shot 2.
- A new outfit each shot because nobody wrote it down.
- A celebrity's name as a shortcut for a look (never: a real person's likeness needs their own reference and consent).
- Making all the shots before approving the character.

See also: `screen-direction`, `skills/character-sheet.md`, `skills/anchor.md`.
