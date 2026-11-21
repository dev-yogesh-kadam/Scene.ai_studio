id: continuity-recall
title: Craft Continuity Recall
version: 3
desc: Keeps returning characters, props and places consistent across clips
description: Use when a multi-clip video needs things that return after several clips (a character, prop, or location) to look the same as when they were last seen, or the user asks for "smart referencing". Keeps one labelled keyframe per generated shot and, before each new clip, picks only the keyframes that clip needs. Craft skill: works inside any workflow and for any video model, alone or alongside craft-continuity-chain or craft-continuity-board. Never triggers on its own: load only when the user or another skill explicitly calls for it.
craft: true
words: \b(continuity|smart referenc\w*|keep (her|him|them|it) the same|looks? different (now|again)|consistent (across|between)|same (face|outfit|place) (as|in) (before|shot))\b
---
# Continuity Recall

A memory of what the video has already shown. Every generated shot leaves one labelled keyframe behind. Before the next clip, pick the few that help it most, rather than passing only the last frame or everything.

**Studio:** `video_audio_analysis` with `detect_shots` is film shots {"video", "save_to"}; `extract_key_frames` and step 3's caption strip are film keyframes {"video", "shots", "pick": "middle", "labels", "save_to": "/continuity/recall/keyframes/c<n>"}, which keeps each frame and a copy with its label in a strip below it (keyframe_captioned); the grid is film board {"stills": [{"image": each pick's keyframe_captioned item}], "panels": 6, "numbered": true}. The grid goes in the video model's numbered reference pictures, after the anchor and the sheets (its last @Image). Who someone is comes from NeuralCore (/cast, and a look of its own when they changed).

## Saving keyframes
After each kept clip (never a discarded take):
1. Split it at its cuts (`video_audio_analysis` with `detect_shots: true`), then take one clear frame per shot with `extract_key_frames`: the one that shows its subjects best.
2. Write a short label covering what's in it, with no clip or shot numbers:
   `Maya and Ravi, kitchen, wide from the door, evening, Maya's sleeve torn`
3. With `ffmpeg_job` (see **ffmpeg-recipes**), add a small caption strip BELOW the frame and write the label there. Never write it on the picture itself.
4. Save it in the keyframe library at `/continuity/recall/keyframes/<k>`: image, label, clip, shot, so it survives a resume.

## Picking for the next clip
1. List what the clip needs: who appears, where, which props, in what state, and from what angle.
2. For each need, read the labels and pick the best match. Match the subject first, then the state and angle, then prefer the most recent.
3. Pick only keyframes that add something the character sheets and location plate don't: how a place was lit and framed, or a costume or prop that changed on screen.
4. Keep it lean: one pick per need, 6 at most per clip.

## Build the reference grid
1. Order the picks by when the next clip uses them: the first shot's needs first.
2. With `ffmpeg_job`, tile them, captions included, into ONE grid image that reads left to right, top to bottom, and number each panel in that order. Lay it out by the stills' shape so the whole grid stays between 0.4 and 2.5 times as wide as tall (video models reject other shapes): 16:9 stills in 2 columns × 3 rows, 9:16 stills in 3 columns × 2 rows, 1:1 either way.
3. Save it at `/continuity/clips/<n>` (n: the clip number the inputs give): `grid`, and `panel_lines`, one line per panel saying what to take from it. Call it "this grid", never by an @Image tag; the prompter adds its own. For example:
   `This grid holds numbered reference panels in shot order, read left to right, top to bottom. Panel 1 is the kitchen as seen earlier; use only its layout and lighting for shot 1. Panel 2 is Maya's torn sleeve; keep it in shots 2–3. Render none of the grid's numbers, captions, or panel edges.`

Identity still comes from the character sheets and location plate; the grid shows how things looked on screen.

**Studio:** a change that shows on screen and recurs gets a look entry of its own the first time ("Maya - torn sleeve", book_save). When a review says someone looks different, retake with their NeuralCore entry (or look) as the reference and the label's words in the prompt; after two failures, offer to make a new character sheet instead.
