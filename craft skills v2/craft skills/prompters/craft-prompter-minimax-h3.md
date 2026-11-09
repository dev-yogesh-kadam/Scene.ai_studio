---
name: craft-prompter-minimax-h3
label: Craft MiniMax H3 Prompter
user_description: Written scene → a MiniMax H3 video, assets tagged and settings set
description: 'Use when a video must be generated on MiniMax H3 (`minimax_h3`, or `minimax_h3_max` when named): a written scene is given, or the user asks for an H3 generation. Owns the video_create_edit call: which assets go in, how they are tagged and bound in the prompt, and the call settings. Not for other video models, and not for edits or extensions (H3 has no V2V). Never triggers on its own: load only when the user or another skill explicitly calls for it.'
---

# MiniMax H3 Prompter

Owns the `video_create_edit` call on MiniMax H3. It never changes what happens in the scene —
only how it is wired, tagged, and sent. Load `video-guide-minimax` first: its limits and input
rules stand, and this skill only adds inputs, wiring, and the prompt layout.

```
0 Inputs → 1 Over the limit → 2 Call mode → 3 Wire + tag → 4 Audio → 5 Continuity → 6 Prompt structure → 7 The call
```

## 0 — Inputs

This skill works with whatever inputs arrive. Take each
field from, in order: the inputs (or the state paths they name) → the chat (attachments, canvas
assets, the user's words) → one AskUserQuestion, only for a field the mode requires.

```
mode            generate | frames | reference               inferred when absent
goal            one line: what happens                      REQUIRED

characters      per character: name, sheet(s), anchor (age / build / key features),
                voice_sample, speaks (y/n), variant (age / outfit / state)
location        plate(s), layout, light, time, weather, ambience, music
props           per prop: image, description, holder, count
keyframes       first / last images (no middle frame on H3)
grid            staging grid image + highest panel number, or a reference grid + one line per panel
anchor          staging anchors in order: image + who stands where, in set terms
motion_clip     2-15 s clip for motion / camera / style    minimax_h3_max only

opening         positions, facing, gaze, props at frame one
shots           per shot: framing, lens, angle, action, acting,
                dialogue (speaker, language, line, audio clip), sfx,
                camera move, timing
end_state       final positions, prop ownership
style           show look (grade, texture, realism / animation)
locks           scene-specific must-stay items

dialogue_clips  recorded line clips, in order, with lengths
language        default dialogue language; hindi_mode: prelock | recorded
on_screen_text  exact text to show, or none

duration        seconds                                     from the shots
aspect_ratio                                                required in reference mode; omitted on frames
resolution
audio           on | off      off: the prompt says "No dialogue. No music." (§4)
shot_number

retake          shot number, slot length, anchor frame, what is wrong
copyright_map   original → substitute; no original name may appear in the prompt
```

Required per mode — ask only when one is missing:
- generate: `goal` · frames: `goal` + a first or last frame · reference: `goal` + the reference.

An edit or extension request cannot run on H3: say so in chat and stop — never fake it
with a fresh generation.

Missing optional fields leave their blocks out (§6). With no written scene, write only what
the user said — do not add camera, light, or acting they did not ask for.

**Returns** (in the chat reply): what was generated, references dropped, settings locked, and any
gap sent back with its reason.

## 1 — Over the reference limit

Over a limit in `video-guide-minimax` → keep, in order: assets the user or inputs named, the anchors,
character sheets of on-screen speakers, the location plate, sheets of non-speaking characters,
then props. Drop the rest (their identity rides on text) and say which in chat. Fewer, cleaner
references beat many loose ones.

Dialogue clips are all or nothing: H3 takes 3 audio clips and 15 s in total, so most dialogue
scenes cannot carry recorded lines. If a scene's clips do not fit, wire none, generate with
native voices (or voice samples), and report the scene as needing a redub.

## 2 — Call mode

| Mode | Inputs | Notes |
|---|---|---|
| Generate | Prompt only | — |
| Frames | First and/or last frame | No sheets, plates, or audio alongside. Describe only motion and camera. |
| Reference | Images (+ audio; + motion clip on `minimax_h3_max`) | The pipeline default: sheets and plates carry identity. |

Frames mode trades identity references for a locked opening image — use it only when the
inputs ask for a fixed first or last frame.

## 3 — Wire and tag

- **Wire only assets with a role. Give every reference one job.** Never cite a tag you did not
  wire.
- **One role line per wired asset, one subject per line**, under ASSETS:
  ```
  @Image1: Meera — face, hair, and clothing.
  @Image2: the courtyard — layout, architecture, and light; ignore any people in it.
  @Image3: the brass lantern — shape, material, and color.
  @Video1: camera movement and pacing only (minimax_h3_max).
  ```
- **Same wording every time** for a recurring character (hair, wardrobe, props), in every shot
  and every clip of the show — H3 holds identity by matching words.
- **Identity text stays minimal**: age + build + unique visible features + action-critical
  details. Small text, logos, and key colors are stated in words too.
- **One image, one subject.** A single-character sheet never defines two on-screen characters.
  Several views of one subject: say they jointly define one entity.
- **Never** wire extracted video frames or QC sheets as identity references. Identity always
  comes from the sheets and plates.

## 4 — Audio

- Native audio is always on — `generate_audio` is ignored. A silent clip must be asked for in
  the prompt: "No dialogue. No music."
- **Voice sample**: on the character's role line, `voice: match the voice in @AudioN; never use
  it for any other character.`
- **Recorded dialogue clips** (only when they fit, §1): one tag per line, in dialogue order,
  never merged, no voice samples alongside. Bind each on the speaker's role line (`speaks
  @Audio1 and @Audio3; these clips belong only to <name>`) and at its landing moment (`<name>
  speaks @Audio2 here, lips syncing to it word for word; everyone else's lips stay still`). Add
  to the locks: `Use the attached @Audio clips strictly as-is.` `duration` ≥ summed clip
  lengths + the action between lines.
- Dialogue is quoted and bound to its speaker: `Meera says: "Sign here, please."`

## 5 — Continuity (the inputs say which)

H3 cannot continue from a clip. Choose by the inputs:
- **Text continuity** (reference mode, the default): OPENING restates the previous clip's end
  state as present fact — positions, postures, props, light — with the sheets and plate wired.
  Never "previous", "earlier", or a clip number in the prompt.
- **Staging grid** (reference mode): wire it as an image with the role line `@ImageN: this scene
  so far as numbered panels in time order — the highest-numbered panel is the exact state this
  clip opens from; lower panels are history. Render none of the grid's borders, numbers, or
  tiling.`
- **Reference grid** (reference mode): wire it as an image, its role line its panel lines, word
  for word, its @ImageN tag in place of "this grid".
- **Frame continuity** (frames mode): the previous clip's last frame as the first frame. Locks
  the join but drops the sheets — identity drifts across clips; use it only when the inputs
  ask.
- **Anchor** (reference mode): wire each anchor first among the images with the role line
  `@ImageN: shows the place with everyone where they stand and its light: a reference for
  space and positions, not a frame to copy; faces and looks come from the sheets.`
  It stacks with every reference-mode option here, Fresh start included.
- **Fresh start**: sheets and plate only.

## 6 — Prompt structure

MiniMax publishes no prompt layout; these are the shared prompter blocks, kept short (prompt cap
in `video-guide-minimax`). Each opens with its label on its own line; leave out a block only
when the inputs have nothing for it.

```
GOAL
One line: what happens, who, where.

ASSETS
One role line per wired @tag (§3, §4).

SCENE
Layout, light source, time, weather, ambience, music bed.

OPENING
Who is where, facing, gaze, props held (or the restated end state, §5).

SHOTS
[0-2s] framing + lens + angle → one clear action + acting → {dialogue} → camera move.
[2-5s] …
Timecodes cover the whole duration. One clear action or emotional change per beat, one primary
moving subject. Camera in plain cinematography words ("slow push-in", "locked-off tripod shot").

STYLE
Look, grade, texture — set once.

END STATE
Final positions and prop ownership.

LOCKS
Identity, wardrobe, counts, props, screen direction, the §4 audio-as-is lock, and short "No …"
constraints placed beside what they protect ("No hard cuts. No on-screen text.") — H3 has no
negative-prompt input.
```

**Frames mode**: ASSETS names the frame ("@Image1 is the first frame"); SHOTS describe only motion
and camera.

Every line comes from the inputs; this skill only places it. A feeling in the inputs goes in as its visible tell only ("knuckles whiten on the glass", not "she is afraid"); drop a feeling with no tell.

## 7 — The call

`video_create_edit`, with settings taken from the inputs — unlike the tool's default, do not
ask the user for duration, aspect ratio, or audio:
- `model_name`: `"minimax_h3"` (`"minimax_h3_max"` only when the inputs or user name it, or a
  motion clip is wired)
- `prompt`: the finished prompt, verbatim. No ratio, duration, or resolution text inside it.
- `duration`: whole seconds, fractions rounded up.
- `aspect_ratio`: always set in reference mode (the prompt cannot set the shape); omitted in
  frames mode.
- `resolution`: omit when the inputs give none.
- `shot_number`: the inputs' shot or clip number.

Dropped references, locked settings, and anything the model cannot do go in the chat reply,
never in `prompt`.
