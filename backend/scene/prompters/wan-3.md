id: wan-3
title: Wan 3.0 (and Prime)
workflows: ^video/@wan_3_0
length: 120 to 300 words for a clip of one or two shots; up to 900 for a long multi-shot clip
limit: 1400
---
Wan 3 reads Alibaba's five-section layout. When the craft Wan 3 prompter is loaded, its §6 is the layout and its rules
win; this guide is for any other Wan 3 prompt and is the prompter's "video-guide-wan". Labels in square brackets, each
on its own line; [Core Task] and [Plot Summary] always appear, the rest only when there is something for them:

[Core Task]
The goal in one sentence. One role line per reference the step fills, cited by its tag (the reference pictures @Image1,
@Image2 … in slot order; the Reference video @Video1; the reference sounds @Audio1 …): "Maya corresponds to @Image1,
adopting facial features, hairstyle, and clothing." "The location references @Image4, adopting spatial layout,
architecture, and lighting; the people in the image are ignored." A voice: "the timbre of Maya references @Audio1".
Partial borrowing is said: "Use only the color palette and lighting of @Image2, not its characters." Then the look:
"The whole film adopts <style>."

[Plot Summary]
1. Opening: who is where, facing, gaze, props held.
2. Shot 1 [0-3s]: framing + lens + angle → action + acting, citing each reference every time it is used ("Maya
   (@Image1) lifts the lantern (@Image3)") → camera move. Dialogue in quotes, bound to its speaker.
N. End: final positions and who holds what.
Shots run 2–5 s each and together cover the whole length.

[Audio Style]
Dialogue language and accent, ambience, each sound effect in its own sentence, the music, or "No background music."
No dialogue: the characters stay naturally silent, and which sounds remain.

[Camera & Core Constraints]
Camera rules for the whole clip, cuts only where stated, identity, wardrobe, counts, props, screen direction.

[Negative Prompts]
Comma-separated exclusions, plus "subtitles" when there is no on-screen text.

Rules:
- Modes: frames (a first and last frame, nothing else beside them: describe motion and camera only), reference
  (pictures and sounds carry identity: the default), edit and extend (the source clip in the Reference video slot,
  @Video1; extend says the direction in [Core Task]: "Continue @Video1 forward after its last frame").
- A reference video is 15 s at most in all; a clip to continue keeps its last 15 s, and source plus new is 30 s at
  most. Sound is never wired without a picture or a source clip.
- Sound is a setting (Sound: on) whenever there is dialogue, sound or a wired sound.
- No shape, length, resolution or frame-rate words anywhere.
