---
name: script-to-video
label: Script to Video
command: true
user_description: Script, audio, idea or brief → video, images or a detailed script
description: 'Use when the user wants a script, audio, idea or brief turned into a video, a set of images or a detailed script ("script to video"). Runs the craft skills in order (asset-designer → director → continuity → prompter) and owns every choice between them: the questions, the models, and what each skill is given. Not for a single image or one-off clip.'
---

# Script to Video

```
1 Input → 2 Setup → 3 Models → 4 Assets → 5 Direct → 6 Generate
```
This skill only runs the workflow. Each craft skill does its own work and saves it at its own path (State, below). Load each one with `load_skill` when its step comes and tell it the exact state paths to read. Never point the prompter at a whole folder: name the one clip, and only the sheets that clip needs.

## 1 — Input
Ask with AskUserQuestion: "What are you starting from?" with the options Script, Audio, Idea, Brief, then take what they paste or upload. Skip the question when the message already carries it. Images the user attached go to asset-designer as `characters`, `locations`, `props`. Voice samples they attach are saved per speaker (a character, or the narrator).
- **Script, Idea, Brief:** used as the `script` as given; for Video and Images an Idea or Brief becomes a story first (§4).
- **Audio:** one `video_audio_analysis`, with the script if there is one. Its timestamped transcript (per line: start, end, speaker, words) becomes the `script`, the audio's length the `runtime`. Speakers take the script's names; anyone still unnamed gets a short working name; the narrator is marked `narrator`. The audio itself is kept for the final cut.

Save `/s2v/input`: script, runtime, audio, voices/<name>.

## 2 — Setup
One AskUserQuestion round with all four questions:
1. **Aspect ratio:** 16:9 (Default), 9:16, 1:1.
2. **Resolution:** 4K, 1080p, 720p (Default), 480p.
3. **Convert the script into:** Video, Images, Detailed script.
4. **Continuity method (video only):** Board, Chain (Default), Recall.

Answers that don't apply are ignored: continuity for Images and Detailed script; resolution for Images (the mode sets it) and Detailed script; aspect ratio for Detailed script.

**Style** (Video and Images only; Detailed script skips it): once every answer is in, show the style picker: `preset_search` with `query: "art style"`, `categories: ["art-styles"]`, `limit: 20`, `present_to_user: true`. The user's pick is the style for the whole run and never changes. Save its slug and its `body.prompt` word for word, never paraphrased. A skip or no results: realistic.

Save the answers and the style in `/s2v/setup`.

## 3 — Models
The mode the user picked in the chat decides the models. The agent sees it as a note on the turn: "Available video models for this conversation: …" and "Available image models for this conversation: …". No note: the picker is on automatic; use `seedance_2_5` and `seedream-5-0-pro`.

| Video model | Prompter |
|---|---|
| `seedance_2_5` | prompter-seedance-2-5 |
| `seedance_2_0`, `seedance_2_0_fast`, `seedance_2_0_mini` | prompter-seedance-2 |
| `wan_3_0`, `wan_3_0_prime` | prompter-wan-3 |
| `minimax_h3`, `minimax_h3_max` | prompter-minimax-h3 |

- A video model with no prompter: tell the user which models this skill supports and stop.
- **Continuity:** Chain runs on `seedance_2_5`, `wan_3_0` and `wan_3_0_prime`. On Seedance 2.0 (weak video-to-video) and MiniMax (can't extend a clip) Chain becomes Board, said in one line. Board and Recall work on every model.
- **Resolution:** 4K = `2160p`. Above what the video model offers, use its highest and say so. Images take the resolution the mode sets.

Save the video model, image model and prompter in `/s2v/setup`.

## 4 — Assets
Video and Images only. An Idea or Brief first becomes a story: load **director** with it and `format: story`, and save `/director/story` as `/s2v/input/script`, so the sheets cover everyone the story has.

Then load **asset-designer** with:
- `script`: `/s2v/input/script`;
- `style`: `/s2v/setup/style_preset` and `/s2v/setup/style_prompt`;
- `characters`, `locations`, `props`: the user's images.

It asks the references question and saves the sheets at `/characters`, `/locations`, `/props`.

## 5 — Direct
Load **director** with:
- `script`: `/s2v/input/script`; `runtime`: `/s2v/input/runtime` (audio input only);
- `style`: `/s2v/setup/style_preset` and `/s2v/setup/style_prompt` (Video and Images);
- `format`: Video → `video`, Images → `image`, Detailed script → `story`;
- `target_model`: `/s2v/setup/video_model` (Video only);
- `aspect_ratio`: `/s2v/setup/aspect_ratio` (Video and Images);
- `characters`, `locations`, `props`: the sheet paths asset-designer saved.

It saves its output at `/director`. Detailed script ends here: post `/director/story`.

## 6 — Generate
**Images:** one `image_create_edit` per frame `/director/frames/<n>`, all in one response, with `/s2v/setup/image_model`: its `image_description`, then `/s2v/setup/style_prompt` word for word, as the prompt; the sheets its `cast` names, in those looks, as references; the aspect ratio from `/s2v/setup`. Save each image at `/s2v/frames/<n>/image`.

**Video:** clip by clip in order, from clip 1. For each clip n:

1. **Continuity**, by its join (`/director/clips/<n>/join`) and the method:

   | Method | `continues` | `cut` | `new place` |
   |---|---|---|---|
   | Chain | continuity-chain (extends the clip before) | normal generation | normal generation |
   | Board | continuity-board (the scene's grid) | continuity-board | normal generation, new grid |
   | Recall | continuity-recall | continuity-recall | continuity-recall |

   Load it with: clip `/director/clips/<n>`, the clip number n, previous video `/s2v/clips/<n-1>/video`, and Board's grid `/continuity/board/<scene>`. It saves its fields at `/continuity/clips/<n>`.

2. **Prompter**, given exactly these paths:
   - clip: `/director/clips/<n>`;
   - continuity: `/continuity/clips/<n>`, when it ran;
   - sheets: only those the clip's `cast` names, in the look it names: "Maya - torn sleeve" → `/characters/maya/looks/torn_sleeve`, "Kitchen - night" → `/locations/kitchen/sheets/night`;
   - voices: `/s2v/input/voices/<name>` for each speaker in the clip, when the user gave one;
   - setup: `/s2v/setup`.

   | Prompter field | From |
   |---|---|
   | `goal` | clip `goal` |
   | `location` | clip `scene`, and the place's sheet |
   | `opening` | continuity `opening` when it wrote one, else clip `opening` |
   | `shots` | clip `shots`, with `voiceover` as the narrator's off-screen lines (audio input: the voiceover only times the shots and is never voiced) |
   | `end_state` | clip `end_state` (continuity's when it wrote one) |
   | `locks` | clip `locks`, plus continuity `locks` |
   | `style` | `/s2v/setup/style_prompt` word for word, then the look in `/director/plan/bible` |
   | `characters`, `props` | the sheets above; each speaker's voice as their `voice_sample` (the narrator's rides with the voiceover) |
   | `dialogue_clips` | audio input: each on-screen line in the clip, cut from `/s2v/input/audio` at its transcript times with `ffmpeg_job`, one clip per line, a line under 2 s padded with silence at its end to 2 s (`-af apad=whole_dur=2`); narrator lines are never cut, they go on at the final cut |
   | `duration` | clip `time_range` |
   | `shot_number` | n |
   | `aspect_ratio`, `resolution` | `/s2v/setup` |
   | `audio` | on (audio input: the clip's sound is replaced by the original audio at the final cut) |
   | `mode`, `direction`, `source_video`, `grid` | continuity (Board: its grid and highest panel; Recall: its grid and `panel_lines`) |

   Save the video at `/s2v/clips/<n>/video`.

3. **After every clip**, whatever its join, before the next clip: under Board, its stills go into `/continuity/board/<scene>` (a `new place` clip starts the scene's grid); under Recall, its keyframes go into `/continuity/recall/keyframes`. Chain needs nothing.

Under Chain and Board, a clip that starts with a normal generation waits on nothing and can go out alongside the others.

## State
```
script-to-video   /s2v/input              script, runtime, audio, voices/<name>
                  /s2v/setup              input, format, aspect_ratio, resolution, continuity, style_preset, style_prompt, video_model, image_model, prompter
                  /s2v/clips/<n>/video    /s2v/frames/<n>/image
asset-designer    /characters/<name>      /locations/<name>      /props/<name>
director          /director/plan          /director/scenes/<s>   /director/clips/<n>   /director/frames/<n>   /director/story
continuity        /continuity/clips/<n>   /continuity/board/<scene>   /continuity/recall/keyframes/<k>
```
