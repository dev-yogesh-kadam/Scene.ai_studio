---
name: prompter-seedance-2-5
label: Seedance 2.5 Prompter
description: 'Use when a video must be generated on Seedance 2.5 (`seedance_2_5`): a written scene is given, or the user asks for a Seedance 2.5 generation. Owns the video_create_edit call: which assets go in, how they are tagged and bound in the prompt, and the call settings. Not for other video models.'
---

# Seedance 2.5 Prompter

Owns the `video_create_edit` call on `seedance_2_5`. It never changes what happens in
the scene — only how it is wired, tagged, and sent.

```
0 Inputs → 1 Over the limit → 2 Call mode → 3 Wire + tag → 4 Audio → 5 Continuity refs → 6 Prompt structure → 7 The call
```

## 0 — Inputs

This skill works with whatever inputs arrive. Take each
field from, in order: the inputs (or the state paths they name) → the chat (attachments, canvas
assets, the user's words) → one AskUserQuestion, only for a field the mode requires.

```
mode            generate | reference | edit | extend      inferred when absent (video + "extend" → extend)
goal            one line: what happens                    REQUIRED

characters      per character: name, sheet(s), anchor (age / build / key features),
                voice_sample, speaks (y/n), variant (age / outfit / state)
location        plate(s), layout, light, time, weather, ambience, music
props           per prop: image, description, holder, count
source_video    clip + length + role (continue | extend | edit | reference | blockout)
direction       forward | backward                        extend only
keyframes       first / middle / last images
grid            staging grid image + highest panel number, or a reference grid + one line per panel

opening         positions, facing, gaze, props at frame one
shots           per shot: framing, lens, angle, action, acting,
                dialogue (speaker, language, line, audio clip), sfx,
                camera move, timing, transition
end_state       final positions, prop ownership
style           show look (grade, texture, realism / animation)
locks           scene-specific must-stay items

dialogue_clips  recorded line clips, in order, with lengths
language        default dialogue language; hindi_mode: prelock | recorded
on_screen_text  exact text to show, or none

duration        seconds                                   locked by mode, else from the shots
aspect_ratio                                              locked by source / keyframe when present
resolution
audio           on | off                                  By default on
shot_number

retake          shot number, slot length, anchor frame, what is wrong
copyright_map   original → substitute; no original name may appear in the prompt
```

Required per mode — ask only when one is missing:
- generate: `goal` · reference: `goal` + the reference · edit: `source_video` + the change ·
  extend: `source_video` + `direction` (when no next action is given, continue the clip's own
  flow).

Missing optional fields leave their blocks out (§6). With no written scene, write only what
the user said — do not add camera, light, or acting they did not ask for.

**Returns** (in the chat reply): what was generated, references dropped, settings locked, and any
gap sent back with its reason.

## 1 — Over the reference limit

Over a limit in `video_create_edit`'s seedance_2_5 caps → keep, in order: assets the user or inputs named, character sheets and the
location plate of on-screen subjects, the source video, dialogue clips, then props. Drop the
rest (their identity rides on text) and say which in chat. Never drop some of a scene's
dialogue clips and keep others — partial coverage hands lines to the wrong speaker.

## 2 — Call mode

Decided by the reference video. One mode per call.

| Mode | When | Locked |
|---|---|---|
| Generation | No reference video | — |
| Reference generation | Video used only for motion, camera, blockout, or continuity; or the target ratio or length differs from it | — |
| Editing | Change something inside the same clip, same ratio, about the same length | Ratio + length = source |
| Extension | New content before or after the clip | Ratio = source |

- Seedance 2.5 treats most video references as edits. For **reference generation**, put this
  exact sentence right after the prompt's goal sentence: `Please note that this is not video
  editing.` Never in any other mode.
- Editing: `duration` = the source clip's length, rounded up. Extension: `duration` = the new
  segment's length.
- Edit and extend in one request → two calls: edit first, then extend the edited clip.
- Keyframes: the first-frame image's ratio locks the output ratio; first and last frames must
  share a ratio.

## 3 — Wire and tag

- **Wire only assets with a role.** Never cite a tag you did not wire. Never put a tag in a shot
  where that subject is absent — the model forces it into frame.
- **One role line per wired asset, one subject per line.** Never a range ("A and B reference
  @Image1 and @Image2").
  ```
  <Character A> maps to @Image1; use only facial features, hairstyle, and clothing.
  <Prop A> maps to @Image3; use only structure, material, and color.
  <Location> references @Image4; use only spatial layout, architecture, and lighting; do not use the people in the image.
  @Video1 is used for <action / camera movement / pacing>; do not use its characters, clothing, or scene.
  ```
- **Identity text stays minimal**: age + build + unique visible features + action-critical
  details, then `100% matches the reference`. Long appearance text fights the image. Small text,
  logos, and key colors are stated in words too — the model drops them otherwise.
- **One image, one subject.** A single-character sheet never defines two on-screen characters.
  Several views of one subject: say they jointly define one entity.
- **Keyframes** go inside `reference_image_urls` at their tag position. Use these exact
  standalone sentences, each followed by one sentence on what the frame defines (positions,
  poses, props, camera direction):
  - `Use @ImageN as the first frame.` / `Use @ImageN as the last frame.`
  - Several in order: `Use @Image1 through @ImageN as keyframes in that order.`
  - Every other image: `… without changing the first-frame composition defined by @Image1.`
- **Storyboard grid image**: `@ImageN provides the shot order and approximate compositions for
  an N-panel grid. Read it left to right, top to bottom; do not adopt its sketch style, borders,
  numbers, or text.`
- **Never** wire extracted video frames or QC sheets as identity references — rendered artifacts
  compound clip over clip. Identity always comes from the sheets and plates.

## 4 — Audio

- **Voice sample** (a speaking character with a sample): wire it and bind it on that character's
  role line: `voice: @AudioN — match this voice's timbre, accent, pace, and pitch exactly; never
  use it for any other character.` Non-speaking characters get no sample.
- **Recorded dialogue clips** (one clip per line): wire them in dialogue order, one tag per line,
  never merged into one file, no voice samples alongside. Bind each tag twice:
  - on the speaker's role line: `speaks @Audio1 and @Audio3; these clips belong only to <name>,
    no other character voices them.`
  - at its landing moment: `<name> speaks @Audio2 here, lips syncing to it word for word;
    everyone else's lips stay still.`
  - once in the locks: `Use the attached @Audio clips strictly as-is — same pronunciation and
    voice; do not re-voice, re-synthesize, or translate any line, and no character speaks a word
    that is not in these clips.`
  - `duration` ≥ summed clip lengths + the action between lines.
- Written dialogue wins over what a reference clip says; a clip gives the voice only, unless the
  inputs say to reuse its words.
- `generate_audio: true` whenever audio is wired or the prompt has dialogue or sound.

## 5 — Continuity references (the inputs say which)

- **Continue a clip**: wire the previous approved clip as `reference_video_url` and bind it:
  `@Video1 shows this exact scene up to the moment this clip begins. The clip continues that
  action, beginning the instant after @Video1's final frame — same place, same light, zero pause,
  no fade.` Sheets and plate are still wired for identity.
  - Source over 30 s → `ffmpeg_job` keeps the last 29 s
    (`["-sseof","-29","-i","clip.mp4","-c","copy","ref.mp4"]`); never trim the end — the final
    frame is the join.
- **Staging grid**: wire it as an image and bind it: `@ImageN shows this scene so far as numbered
  panels in time order — the highest-numbered panel is the exact state this clip opens from;
  lower panels are history. Render none of the grid's borders, numbers, or tiling.`
- **Reference grid**: wire it as an image and bind it with its panel lines, word for word, its
  @ImageN tag in place of "this grid".
- **Fresh start**: sheets and plate only.

## 6 — Prompt structure

Write these blocks in this order, each opening with its label on its own line. Leave out a
block only when the inputs have nothing for it.

```
GOAL
One line: what happens, who, where. The §2 "not video editing" sentence goes right after it.

ASSETS
One role line per wired @tag — images, video, and audio (§3, §4, §5 bindings).

SCENE
Layout (foreground / midground / background), light source, time, weather, ambience, and any
music bed.

OPENING
Who is where, facing, gaze, props held. Or the keyframe sentence, the @Video1 continue line, or
the grid line (§3, §5).

SHOTS
Shot 1: framing + lens + angle → action + acting → {dialogue} @AudioN / <sfx> → camera move.
Shot 2: …  Timed ("0–4 s") when the inputs time it.

STYLE
Look, grade, texture — set once for the whole clip.

END STATE
Final positions and prop ownership.

POSITIVE LOCKS
Identity, wardrobe, counts, props, screen direction, cuts only where stated, no subtitles, no
music when there is none, and the §4 audio-as-is lock when clips are wired.
```

**Editing mode (§2)** uses its own blocks — the source clip already holds the scene and shots:

```
EDIT GOAL
Edit @Video1, changing only <object, region, or sound> to <target>.

SOURCE
@Video1 is the sole editing master and governs the scene, camera, action paths, occlusion, and
event order.

ASSETS
Role lines for the target material (@ImageN / @AudioN).

EDIT SCOPE
What changes, its count, what stays. Always close with one of:
- "Except for the objects explicitly modified above, all other visible characters, props, and
  background elements in @Video1 remain unchanged and are not to be replaced or removed."
- (only-keep-targets edits) "Except for the objects explicitly retained above, remove all other
  visible subjects from @Video1; do not add any unspecified objects."

TIMELINE
The new object inherits the timing, path, speed, and occlusion of the one it replaces; all
other action, camera, and cuts stay as in @Video1.
```

Sound-only edits: EDIT SCOPE names the speaker or sound and the time range; the visuals,
lip-sync timing, and every other sound stay as in @Video1.

**Extension mode (§2)**: GOAL is `Extend @Video1 forward` (or backward); OPENING becomes the
boundary — forward: "the first frame continues directly from @Video1's final frame"; backward:
"the final frame connects to @Video1's first frame", plus "nothing that appears only later in
@Video1 appears early". POSITIVE LOCKS adds: "each subject stays one continuous instance — no
duplicates, no splitting".

- Sound syntax inside SHOTS and SCENE: `{dialogue}` with speaker and language, `<sound effect>`,
  `(music)`.
- Every line of a block comes from the inputs; this skill only places it.

## 7 — The call

`video_create_edit`, with settings taken from the inputs — unlike the tool's default, do not
ask the user for duration, aspect ratio, or audio:
- `model_name`: `"seedance_2_5"`
- `prompt`: the finished prompt, verbatim. No ratio, duration, resolution, fps, or audio-toggle
  text inside it.
- `duration`: fractions rounded up (mode locks in §2 win).
- `aspect_ratio`: mode locks in §2 win.
- `resolution`: omit when the inputs give none.
- `generate_audio`: per §4.
- `shot_number`: the inputs' shot or clip number.

Dropped references, locked settings, and anything the model cannot do go in the chat reply,
never in `prompt`.
