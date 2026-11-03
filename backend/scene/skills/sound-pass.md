id: sound-pass
title: The sound pass of a finished video
version: 1
desc: Use when the user asks for the whole sound of a finished video: music under it, a score, "make it sound finished".
craft: true
words: \b(sound pass|score (this|it|the film)|add (background )?music|music (bed|under)|make it sound (finished|good)|bgm|soundtrack (for|to) (this|it|the))\b
---
Not when the user said no music. Not for one sound at one moment: that is a "sound" step on its own.

1. Find the video: the one selected, or the last finished cut of this conversation (read /videos or the state the
   film kept). Know its length and its mood from its prompts and what it shows.
2. Plan one music step on the music workflow: one continuous bed for the whole length (its "duration" the video's
   length), an instrumental unless they asked for a song, described by genre, tempo, instruments and mood, rising
   where the story rises. Give it "save_to": "/audio/music".
3. Then put it under the video: an "assemble" step with the shots in order and "after" the music step, which ducks the
   music under speech and evens the loudness; or, for one video the user already has, a "sound" step with the music
   on the video, the video's own sound kept.
4. Sound effects are not in the studio yet: say so once if the user asks for them, and offer the music bed.
5. When it is made, tell the user what was used and that a different mood is one message away.
