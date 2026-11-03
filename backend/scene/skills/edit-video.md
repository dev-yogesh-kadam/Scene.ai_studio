id: edit-video
title: Editing videos the user already has — cut, join, sound
version: 1
desc: Use to cut, trim, split, join or put music and sound on videos you already have.
words: \b(cut|trim|shorten|split|halve|join|merge|combine|stitch|concat\w*|clip out|crop time|add (music|sound|audio)|background (music|sound)|voice.?over|voiceover|narrat\w*|dub|dubbing|soundtrack|put .*(music|sound)|mix in|translate\w*)\b
---
These tools edit videos the user already has. They are instant and free, and they never change what is in the picture.
Never use "generate" for them: generating makes a different video. Each works on the selected videos, or on the videos
the step names by library id: any video of this project (a take of the run, an item in NeuralCore or "Recent items"),
listed in "uses" with slot "clip", in order. Never ask the user to select videos you can name by id. Only when you
cannot tell which video is meant, return no steps and ask ("sound" may also take its video and sound from "Recent
items").

- "trim": keep the part of video "source" from "start" to "end" seconds. First half of a 6 second video: start 0, end 3.
- "split": cut video "source" into "parts" equal pieces, each saved as its own video. Two halves: parts 2.
- "join": join videos into one: those named in "uses" in that order, else all the selected videos in the order they
  are listed.
- "sound": put a sound on a video. "source" is the video's id, "audio" is the sound's id. "replace" is false to mix it
  under the video's own sound (the usual choice for music) and true to take the place of it. Both can be attached items,
  or the newest video and newest sound in "Recent items" when the user says "this video", "the music you made",
  "attach it". This uses ffmpeg: never answer that you cannot attach audio or cannot use ffmpeg.

"source" is the id of a selected video, or of any video of this project; a selected one's length is given as "seconds". For an editing tool set prompt to "" and
clips to 1.

Speech that does not exist yet is a different thing: an audio workflow makes music and songs, not a spoken voice-over,
and no tool here dubs or translates speech. When the user asks for a voice-over, or for a video's speech in another
language, do not plan a music step for it: say that speech cannot be added to an existing video, and offer to make the
shot again with a prompt that says which language the people speak. ("Continue the conversation" or "add another 5
seconds" is instead a new shot that starts on the attached video — use "start_from", not an editing tool.)
