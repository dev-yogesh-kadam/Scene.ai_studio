id: script-to-video
title: Script to Video
version: 3
desc: Script, idea or brief → video, images or a detailed script
description: Use when the user wants a script, idea or brief turned into a video, a set of images or a detailed script ("script to video"). Runs the craft skills in order (craft-script-writer → craft-asset-designer → craft-director → craft-anchor → continuity → prompter) and owns every choice between them: the questions, the models, and what each skill is given. Not for a single image or one-off clip.
words: \b(script[- ]to[- ]video|(turn|make|convert) (this|my|the) (script|story|audio|brief|idea|screenplay) (in)?to (a )?(video|film|movie|images|pictures|storyboard))\b
---
# Script to Video

```
1 Input → 2 Setup → 3 Story → 4 Assets → 5 Plan → 6 Clips → 7 Anchors → 8 Generate
```
**Studio:** 0 Is this a film? comes first and 9 The cut last: both are the studio's own.
This skill only runs the workflow. Load each craft skill with `load_skill` when its step comes and tell it the exact state paths to read. Never point a skill at a whole folder: name the one clip, and only the sheets that clip needs.

## 0 — Is this a film? (Studio)
This skill is also given to a message that asks for a video when the user picked no skill, so check first, before any question of this skill:
- Not a request now (what the user usually makes, a question about videos, an opinion): answer it in "reply", plan nothing, and ask none of this skill's questions.
- One clip: one subject doing one thing, at most 15 s, no script and no audio given ("a 5 second video of a cat"): make it as one step on a video workflow, in the shape and length the message says (else 16:9 and 5 s), and skip every step below. Say in one line that a longer film from a script or an audio is one message away.
- Anything else (a script, an audio, a story, several scenes or people, longer than one clip): go on with step 1.

## 1 — Input
First, before anything else, AskUserQuestion: "What are you starting from?" with the options Idea, Brief, Script, Broken script. Skip it when the message already carries the material; its kind is then read from it. Then take what they paste or upload, as given. Images the user attached go to craft-asset-designer as `characters`, `locations`, `props`. Voice samples they attach are saved per speaker.

**Studio:** an attached sound is a fifth kind, Audio (an episode, a voiceover, a song with words), the studio's own. It is never an option of the question (a question here takes four): a message with a sound attached already carries its material. Transcribe it (the Transcribe workflow, speaker labels on; the script as SCRIPT when there is one), then transcript into /s2v/input/lines. The speakers take the script's names (transcript with "value"), anyone else a short working name, the narrator "narrator". The lines are the script, of kind Script, so step 3 keeps it word for word; the audio's length is the runtime (/s2v/input/runtime), and the audio is kept for the cut (/s2v/input/audio). A voice sample is kept as a NeuralCore entry of type voice ("Maya's voice").

Save `/s2v/input`: kind, script, voices/<name>. **Studio:** an audio input also keeps lines, runtime and audio there.

## 2 — Setup
The mode the user picked in the chat decides the models, and the models decide the prompter and the continuity methods. The agent sees the mode as a note on the turn: "Available video models for this conversation: …" and "Available image models for this conversation: …". No note: the picker is on automatic; use `minimax_h3` and FLUX.2 dev.

| Video model | Prompter | Continuity |
|---|---|---|
| `minimax_h3`, `minimax_h3_max` | craft-prompter-minimax-h3 | Board, Recall |

A video model with no prompter: tell the user which models this skill supports and stop. Chain is left out where video-to-video is weak (Seedance 2.0) or missing (MiniMax).

**Studio:** the user picks the video model (the studio sets none; see "The model and the resolution"). On zoro, `minimax_h3` is H3 All in One (`video/h3_all_in_one`), for a single shot made on its own; this skill's scene clips are its second option, H3 Chunk (`video/h3_chunk`), made for them (the anchor, up to five character sheets, shot keyframes). The generation server makes models, not workflows: MiniMax H3 and H3 Max, Seedance, Wan 3, Kling, Gemini, Grok and Happy Horse, each the setting model of the one workflow `video/generation_video` (`minimax_h3_max`, `minimax_h3` …); only Seedance takes a first or last frame together with reference images. The Seedance and Wan 3 rows are left out: their prompters are not in this studio, so their prompts follow the workflow's own prompt tips. The workflows the chat chose are the turn's note of available models.

One AskUserQuestion round:
1. **Convert the script into:** Video, Images, Detailed script.
2. **Aspect ratio:** 16:9 (Default), 9:16, 1:1.
3. **Resolution:** the video model's resolutions in `video_create_edit`, 720p (Default). **Studio:** 480p is the Default on every workflow (the quickest); H3 All in One's are 480p, 720p (about twice the time) and 1080p (shots of 10 s or less), H3 Chunk's 480p and 768p; 1080p or 4K is otherwise an upscale after the cut (Upscale video on the canvas), said in one line when asked. Asked unless the conversation's direction already has a "Resolution:" line.
4. **Continuity method (video only):** the model's methods; Chain (Default) where it is offered, else Board (Default). **Studio:** on H3 Chunk that is Board (Default) and Recall; Chain comes back when a workflow that extends a clip is listed.

A question left with one option is not asked; that option is used. Answers that don't apply are ignored: continuity for Images and Detailed script; resolution for Images (the mode sets it) and Detailed script; aspect ratio for Detailed script.

**Style** (Video and Images only): once every answer is in, show the style picker: `preset_search` with `query:` every sub-category the <presets> block lists for `art-styles`, space-separated and nothing else (e.g. "anime illustration painterly realistic"; a style sharing no word with the query is dropped from the card), `categories: ["art-styles"]`, `limit: 20`, `present_to_user: true`. The user's pick is the style for the whole run and never changes. Save its slug and its `body.prompt` word for word, never paraphrased. A skip or no results: realistic. **Studio:** the art styles are preset_search's category art-styles ("op" "art-styles" with an empty "query" lists them all). Until the picker card exists, ask with "question", up to four of them, realistic first; keep the pick's id as style_preset and its "words" as style_prompt, word for word.

Save `/s2v/setup`: output, aspect_ratio, resolution, continuity, style_preset, style_prompt, video_model, image_model, prompter.

## 3 — Story
A full script (`kind` Script) for Video or Images skips this step: save `/s2v/input/script` word for word at `/script/story`. Otherwise, AskUserQuestion: "How long should the story run?" with the options 1 min, 3 min (Default), 5 min, 8 min; skip it when the user already named a length. Save the answer as `/s2v/input/runtime`, then load **craft-script-writer** with `script`: `/s2v/input/script` and `runtime`: `/s2v/input/runtime`. It posts the story in chat and saves it at `/script/story`. Detailed script ends here.

## 4 — Assets
Load **craft-asset-designer** with:
- `script`: `/script/story`;
- `style`: `/s2v/setup/style_preset` and `/s2v/setup/style_prompt`;
- `characters`, `locations`, `props`: the user's images.

It asks the references question and saves the sheets at `/characters`, `/locations`, `/props`.

## 5 — Plan
Load **craft-director** with:
- `story`: `/script/story`;
- `characters`, `locations`, `props`: the sheet paths craft-asset-designer saved;
- `style`: `/s2v/setup/style_prompt`;
- `aspect_ratio`: `/s2v/setup/aspect_ratio`.

It saves the plan at `/director`. Every scene's beats and shots are saved before step 6 starts.

## 6 — Clips
Video only. One clip per scene, one generation each, packed from `/director/scenes/<n>/shots`. A scene longer than the video model's longest clip in `video_create_edit` splits at shot cuts into the fewest near-equal clips. A flashback beat starts its own clip. A scene under 4 s joins the next scene's clip (the last scene joins the one before). Clips are numbered across the whole piece. **Studio:** H3 Chunk's longest clip is 15 s and its shortest 4 s, with up to 6 shots, one keyframe each. With an audio input, a clip holds whole lines: it starts and ends on its lines' times (/s2v/input/lines), its shots fitted to them (the timing tool works the frames out), and a clip break falls between two lines.

Each clip is written with the prompter's field names, read off the plan and the sheets:

| Clip field | From |
|---|---|
| `scene_n` | its scene |
| `goal` | one line: what this clip shows, who, where; its beats' instructions |
| `cast` | everyone and everything in its shots' `in_frame`, by the names of their sheets, in the look worn here ("Maya - torn sleeve · Kitchen - night · Lantern"); anyone with no sheet as the plan describes them |
| `location` | the place: its layout from the location sheet, the scene's tone, time and weather |
| `opening` | frame one: who is where, facing, gaze, props held (a later clip of a scene: the frame the clip before ends on) |
| `shots` | its shots in order, each: picture — in frame — motion — size · lens · angle · move — tone — length; dialogue as NAME says "<line>" inside its shot |
| `end_state` | the frame its last shot ends on: positions, who holds what |
| `locks` | who and what is on screen and in what state (looks, wounds, props held), screen direction, and "N cuts exactly, only where stated" |
| `duration` | its shots' lengths added up, rounded up to the next whole second |

Save each at `/s2v/clips/<n>`.

## 7 — Anchors
Video and Images. Load **craft-anchor** with `plan`: `/director/scenes`, `clips`: `/s2v/clips` (Images: no clips, so each shot is its own clip, `<scene>_<shot>`), and the sheet paths craft-asset-designer saved. It saves `/anchors/<k>`, each with the clips it serves.

## 8 — Generate
**Images:** one `image_create_edit` per planned shot, all in one response, with `/s2v/setup/image_model`: the shot's picture frozen at the peak of its action, who is in frame and where, its size, lens, angle and tone, then `/s2v/setup/style_prompt` word for word, as the prompt; references: every `/anchors/<k>` whose `clips` holds `<scene>_<shot>` first, then the sheets of everyone and everything in frame, in the looks worn; the aspect ratio from `/s2v/setup`. With an anchor, the prompt opens "Keep the place, its light and where each figure stands from Image 1; the camera is this shot's." Save each at `/s2v/frames/<scene>_<shot>/image`. **Studio:** the image model is FLUX.2 dev unless the chat chose another. Each frame is a "generate" step with "save_to" "/s2v/frames/<scene>_<shot>/image" (its library id is then at .../image/item), and Image 1 is named as the model's prompt guide says (FLUX.2: image 1).

**Video:** clip by clip in order, from clip 1. For each clip n:

1. **Continuity**, by the method:

   | Method | A scene's first clip | A later clip of the same scene |
   |---|---|---|
   | Chain | normal generation | craft-continuity-chain |
   | Board | normal generation | craft-continuity-board |
   | Recall | craft-continuity-recall | craft-continuity-recall |

   Load it with: clip `/s2v/clips/<n>`, the clip number n, previous video `/s2v/clips/<n-1>/video`, and Board's grid `/continuity/board/<scene>`. It saves its fields at `/continuity/clips/<n>`, and runs its own after-clip step before the next clip.

2. **Prompter**, given exactly these paths: clip `/s2v/clips/<n>`; continuity `/continuity/clips/<n>` when it ran; only the sheets the clip's `cast` names, in the look it names ("Maya - torn sleeve" → `/characters/maya/looks/torn_sleeve`, "Kitchen - night" → `/locations/kitchen/sheets/night`); `/s2v/input/voices/<name>` for each speaker in the clip, when the user gave one; setup `/s2v/setup`. The clip's fields go in as named, plus:

   | Prompter field | From |
   |---|---|
   | `anchor` | every `/anchors/<k>` whose `clips` holds n, in order: its image and positions |
   | `opening`, `end_state` | continuity's when it wrote them, else the clip's |
   | `locks` | the clip's, plus continuity's |
   | `style` | `/s2v/setup/style_prompt` word for word, then the era and world from `/director/episode` |
   | `characters`, `props` | the sheets above; each speaker's voice as their `voice_sample` |
   | `shot_number` | n |
   | `aspect_ratio`, `resolution` | `/s2v/setup` |
   | `audio` | on |
   | `mode`, `direction`, `source_video`, `grid` | continuity (Board: its grid and highest panel; Recall: its grid and `panel_lines`) |

   Save the video at `/s2v/clips/<n>/video`.

   **Studio:** each clip is one "generate" step on H3 Chunk with "save_to" "/s2v/clips/<n>/video" (its library id is then at /s2v/clips/<n>/video/item, so the previous video is "$state:/s2v/clips/<n-1>/video/item"), "shot_number" n and "check" naming what must not go wrong in it; the prompter puts every picture and sound in its slot. With an audio input, the clip's own stretch of the recording (film slice at its lines' times, "pad" 2 for a line under 2 s) goes in the voice track slot and the lips follow it, with no voice sample beside it; narrator lines are never put in a clip: they go under the cut.

Under Chain and Board, a scene's first clip waits on nothing and can go out alongside the others.

## 9 — The cut (Studio)
Video only, once every clip is kept: one "assemble" step with the kept clips in order (music only when the user wants it). With an audio input, the film tool's op film with the clips and /s2v/input/audio instead, so the recording plays under the pictures; subtitles if asked.

## State
```
script-to-video       /s2v/input                 kind, script, runtime, voices/<name>
                      /s2v/setup                 output, aspect_ratio, resolution, continuity, style_preset, style_prompt, video_model, image_model, prompter
                      /s2v/clips/<n>             scene_n, goal, cast, location, opening, shots, end_state, locks, duration, video
                      /s2v/frames/<scene>_<shot>/image
craft-script-writer   /script/story
craft-asset-designer  /characters/<name>      /locations/<name>      /props/<name>
craft-director        /director/episode       /director/scenes/<n>   /director/scenes/<n>/beats/<b>   /director/scenes/<n>/shots/<m>
craft-anchor          /anchors/<k>
continuity            /continuity/clips/<n>   /continuity/board/<scene>   /continuity/recall/keyframes/<k>
```
**Studio:** an audio input adds /s2v/input/lines, runtime and audio. A result's library id is at <path>/item: /s2v/clips/<n>/video/item, /s2v/frames/<scene>_<shot>/image/item, /anchors/<k>/image/item.
