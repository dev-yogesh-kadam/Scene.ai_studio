id: seedance
title: Seedance (2.5, 2.0, Fast, Mini, 2.5 Flash)
workflows: ^video/@seedance_
length: 120 to 300 words for a clip of one or two shots; up to 900 for a long multi-shot clip, the blocks carrying the scene
limit: 1400
---
Seedance reads a long prompt in labelled blocks. When a craft prompter is loaded (Seedance 2.5 or 2.0), its §6 is the
layout and its rules win; this guide is for any other Seedance prompt. Write these blocks in this order, each label on
its own line, and leave out a block only when the shot has nothing for it:

GOAL
One line: what happens, who, where. On Seedance 2.5, when a video is given only for motion, camera, blockout or
continuity, the next sentence is exactly: Please note that this is not video editing.

ASSETS
One role line per reference the step fills, one subject each, cited by its tag: the reference pictures are @Image1,
@Image2 … in slot order, the Reference video is @Video1 (more videos @Video2 …), the reference sounds @Audio1 ….
"Maya maps to @Image1; use only facial features, hairstyle, and clothing." A place: "use only spatial layout,
architecture, and lighting; do not use the people in the image." A video for motion: "@Video1 is used for camera
movement and pacing; do not use its characters, clothing, or scene." A voice: "voice: @Audio1 — match this voice's
timbre, accent, pace, and pitch exactly; never use it for any other character." Never cite a tag the step does not
fill, and never put a tag in a shot its subject is not in. On Seedance 2.0 a name follows every tag: @Image1 (Maya).

SCENE
Foreground, midground and background; the light source; time, weather, ambience; the music bed or none.

OPENING
Who is where, facing, gaze, props held at frame one. A clip that goes on from another: its end state as present fact,
never "previous" or a clip number; or "@Video1 shows this exact scene up to the moment this clip begins."

SHOTS
Shot 1 (0–3 s): framing + lens + angle → action + acting → dialogue / sound → camera move. Shot 2 (3–8 s): …
Spoken words in quotes with who says them. One camera move per shot. Acting as what shows ("knuckles whiten on the
glass"), never a feeling with no visible sign.

STYLE
The look, the grade, the texture, once for the whole clip.

END STATE
Final positions and who holds what.

POSITIVE LOCKS
Identity, wardrobe, counts, props, screen direction, "cuts only where stated", no subtitles, no music when there is
none; with recorded lines: "Use the attached @Audio clips strictly as-is — same pronunciation and voice."

Rules:
- Identity in words stays short: age, build, the features that tell people apart, then "100% matches the reference".
  Small text, logos and key colours are said in words too.
- A first or last frame is its own slot ("start_from" and the last frame slot) or a reference picture with "Use @ImageN
  as the first frame."; describe the motion from it, not the picture again.
- Sound is a setting (Sound: on) whenever there is dialogue, sound or a wired sound; the prompt never says "with audio".
- No shape, length, resolution or frame-rate words anywhere.
