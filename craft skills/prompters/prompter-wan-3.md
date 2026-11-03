---
name: prompter-wan-3
label: Wan 3 Prompter
description: 'Use when a video must be generated on Wan 3.0 (`wan_3_0`, or `wan_3_0_prime` when named): a written scene is given, or the user asks for a Wan generation. Owns the video_create_edit call: which assets go in, how they are tagged and bound in the prompt, and the call settings. Not for other video models.'
---

# Wan 3 Prompter

Owns the `video_create_edit` call on Wan 3.0. It never changes what happens in the scene —
only how it is wired, tagged, and sent. Load `video-guide-wan` first: its limits and mode rules
stand, and this skill only adds inputs, wiring, and the prompt layout.

```
0 Inputs → 1 Over the limit → 2 Call mode → 3 Wire + tag → 4 Audio → 5 Continuity → 6 Prompt structure → 7 The call
```

## 0 — Inputs

This skill works with whatever inputs arrive. Take each
field from, in order: the inputs (or the state paths they name) → the chat (attachments, canvas
assets, the user's words) → one AskUserQuestion, only for a field the mode requires.

```
mode            generate | frames | reference | edit | extend   inferred when absent
goal            one line: what happens                          REQUIRED

characters      per character: name, sheet(s), anchor (age / build / key features),
                voice_sample, speaks (y/n), variant (age / outfit / state)
location        plate(s), layout, light, time, weather, ambience, music
props           per prop: image, description, holder, count
source_video    clip + length + role (continue | extend | edit)
direction       forward | backward | both                       extend only
keyframes       first / last images (no middle frame on Wan)
grid            staging grid image + highest panel number, or a reference grid + one line per panel

opening         positions, facing, gaze, props at frame one
shots           per shot: framing, lens, angle, action, acting,
                dialogue (speaker, language, line, audio clip), sfx,
                camera move, timing, transition
end_state       final positions, prop ownership
style           show look (grade, texture, realism / animation)
locks           scene-specific must-stay items
exclusions      what must not appear

dialogue_clips  recorded line clips, in order, with lengths
language        default dialogue language; hindi_mode: prelock | recorded
on_screen_text  exact text to show, or none

duration        seconds                                         from the shots
aspect_ratio                                                    omitted on frames mode
resolution
audio           on | off                                        By default on
shot_number

retake          shot number, slot length, anchor frame, what is wrong
copyright_map   original → substitute; no original name may appear in the prompt
```

Required per mode — ask only when one is missing:
- generate: `goal` · frames: `goal` + a first frame · reference: `goal` + the reference ·
  edit: `source_video` + the change · extend: `source_video` + `direction`.

Missing optional fields leave their content out (§6). With no written scene, write only what
the user said — do not add camera, light, or acting they did not ask for.

**Returns** (in the chat reply): what was generated, references dropped, settings locked, and any
gap sent back with its reason.

## 1 — Over the reference limit

Over a limit in `video-guide-wan` → keep, in order: assets the user or inputs named, character
sheets of on-screen speakers, the location plate, sheets of non-speaking characters, then
props. Drop the rest (their identity rides on text) and say which in chat.

Dialogue clips are all or nothing: if a scene's clips do not fit (count or combined length),
wire none, generate with native voices, and report the scene as needing a redub.

## 2 — Call mode

| Mode | Inputs | Notes |
|---|---|---|
| Generate | Prompt only | — |
| Frames | First frame (+ last frame) | No sheets, plates, or audio alongside. Describe only motion and camera — the image already fixes subject, scene, and style. |
| Reference | Images (+ audio) | The pipeline default: sheets and plates carry identity. |
| Edit | Source clip (+ images) | Source audio is not kept; `generate_audio` decides the new sound. |
| Extend | Source clip (+ images) | Say the direction: after its last frame, into its first frame, or both. |

Frames mode trades identity references for a locked opening image — use it only when the
inputs ask for a fixed first or last frame.

## 3 — Wire and tag

- **Wire only assets with a role.** Never cite a tag you did not wire.
- **One role line per wired asset, one subject per line**, all under [Core Task]:
  ```
  Character A corresponds to @Image1, adopting facial features, hairstyle, and clothing.
  Prop A corresponds to @Image3, adopting structure, material, and color.
  The location references @Image4, adopting spatial layout, architecture, and lighting; the people in the image are ignored.
  ```
- **Repeat the citation every time a reference is used**, in every plot node: "Character A
  (@Image1) lifts the lantern (@Image3)".
- **Partial borrowing** is stated: "Use only the color palette and lighting of @Image2, not its
  characters."
- **Identity text stays minimal**: age + build + unique visible features + action-critical
  details. Small text, logos, and key colors are stated in words too.
- **One image, one subject.** A single-character sheet never defines two on-screen characters.
  Several views of one subject: say they jointly define one entity and generate one instance.
- **Never** wire extracted video frames or QC sheets as identity references. Identity always
  comes from the sheets and plates.

## 4 — Audio

- **Voice sample**: declare it under [Core Task] — `the timbre of <name> references @AudioN` —
  and at the line: `using @AudioN's timbre, <name> says: "<line>"`. Non-speaking characters get
  no sample.
- **Recorded dialogue clips** (one clip per line, in dialogue order, never merged, no voice
  samples alongside): declare each under [Core Task] — `@Audio2 is <name>'s line, used in full`
  — and at its plot node: `<name> speaks @Audio2 here, lips syncing to it word for word;
  everyone else's lips stay still.` Add to [Camera & Core Constraints]: `Use the attached @Audio
  clips strictly as-is — same pronunciation and voice; no character speaks a word that is not
  in these clips.` `duration` ≥ summed clip lengths + the action between lines.
- Audio is never wired without an image or a source clip.
- No dialogue: state that the characters stay naturally silent, and which sounds remain.

## 5 — Continuity (the inputs say which)

- **Continue a clip**: extend mode — wire the previous approved clip as the source, direction
  "after its last frame", plus the sheets and plate as images for identity.
  - Source over 15 s → `ffmpeg_job` keeps the last 14 s
    (`["-sseof","-14","-i","clip.mp4","-c","copy","ref.mp4"]`); never trim the end — the final
    frame is the join.
- **Staging grid** (reference mode): wire it as an image and declare it under [Core Task]:
  `@ImageN shows this scene so far as numbered panels in time order — the highest-numbered panel
  is the exact state this clip opens from; lower panels are history. Render none of the grid's
  borders, numbers, or tiling.`
- **Reference grid** (reference mode): wire it as an image and declare it under [Core Task] with
  its panel lines, word for word, its @ImageN tag in place of "this grid".
- **Text continuity** (reference mode): the first plot node restates the previous clip's end
  state as present fact — positions, postures, props, light. Never "previous", "earlier", or a
  clip number in the prompt.
- **Fresh start**: sheets and plate only.

## 6 — Prompt structure

Alibaba's official five-section layout, filled from the inputs. Labels in square brackets,
each on its own line; [Core Task] and [Plot Summary] always appear, the rest only when there is
content for them.

```
[Core Task]
GOAL in one sentence. Every reference role line (§3, §4). The look: "The whole film adopts
<style>."

[Plot Summary]
1. Opening: who is where, facing, gaze, props held (or the restated end state, §5).
2. Shot 1 [0-3s]: framing + lens + angle → action + acting (@ImageN citations) → camera move.
   Dialogue verbatim and bound to its speaker: <name> says: "<line>".
3. Shot 2 [3-6s]: …
N. End: final positions and prop ownership.
Shots run 2-5 s each and together cover the whole duration; times come from the inputs.

[Audio Style]
Dialogue language and accent, ambience, sound effects (each in its own sentence, optionally
timed), music — or "No background music."

[Camera & Core Constraints]
Camera rules for the whole clip, cuts only where stated, and the locks: identity, wardrobe,
counts, props, screen direction, the §4 audio-as-is lock.

[Negative Prompts]
Comma-separated exclusions from the inputs, plus "subtitles" when on_screen_text is none.
```

**Edit mode**: [Core Task] is `Edit @Video1: <add / delete / replace / change X to Y>; keep the
rest of the frame unchanged.` To keep only the motion: `Replace <subject> in @Video1 with
<name> (@Image1), keeping the action, path, and scene unchanged.` [Plot Summary] covers only
what changes.

**Extend mode**: [Core Task] is `Continue @Video1 forward after its last frame` (or `lead into
its first frame`, or both); the first plot node is the join; [Camera & Core Constraints] adds
"each subject stays one continuous instance — no duplicates".

**Frames mode**: [Core Task] names the first (and last) frame; [Plot Summary] describes only
motion and camera.

Every line comes from the inputs; this skill only places it.

## 7 — The call

`video_create_edit`, with settings taken from the inputs — unlike the tool's default, do not
ask the user for duration, aspect ratio, or audio:
- `model_name`: `"wan_3_0"` (`"wan_3_0_prime"` only when the inputs or user name it)
- `prompt`: the finished prompt, verbatim. No ratio, duration, resolution, or fps text inside it.
- `duration`: fractions rounded up; with a source clip, clip + duration ≤ 30 s.
- `aspect_ratio`: omitted in frames mode.
- `resolution`: omit when the inputs give none.
- `generate_audio`: per §4.
- `shot_number`: the inputs' shot or clip number.

Dropped references, locked settings, and anything the model cannot do go in the chat reply,
never in `prompt`.
