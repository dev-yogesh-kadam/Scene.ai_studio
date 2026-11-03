id: script-to-video
title: A script, audio, idea or brief made into a video, a set of pictures or a detailed script
version: 1
desc: Use when the user wants a script, audio, idea or brief turned into a video, a set of pictures or a detailed script ("script to video"). Not for a single picture or a one-off clip.
next: asset-designer, director, continuity-chain, continuity-board, continuity-recall
words: \b(script[- ]to[- ]video|(turn|make|convert) (this|my|the) (script|story|audio|brief|idea|screenplay) (in)?to (a )?(video|film|movie|images|pictures|storyboard))\b
---
This skill only runs the work: each craft skill it names does its own part and keeps it at its own paths (below).
Read each with read_skill when its step comes, and give it exactly the paths to read. Never give a clip's step more
than that clip needs: its cast, its place, its grid.

1. Input. Ask with "question" "What are you starting from?": Script, Audio, Idea, Brief (skip it when the message
   says). Pictures the user attached go to asset-designer (book_save them under their names); voice samples are kept
   per speaker in NeuralCore as type voice ("Maya's voice").
   - Script, Idea, Brief: the text is the script (read_text with "path": "/s2v/input/script").
   - Audio: transcribe it (the Transcribe workflow, speaker labels on; the script as SCRIPT when there is one), then
     transcript into /s2v/input/lines. The speakers take the script's names (transcript with "value"), anyone else a
     short working name, the narrator "narrator". The lines are the script, the audio's length the runtime
     (/s2v/input/runtime); the audio is kept for the final cut (/s2v/input/audio).
2. Setup: one "questions" round, all at once:
   - Shape: Landscape 16:9 (default), Portrait 9:16, Square.
   - Make it into: Video (default), Pictures, Detailed script.
   - Quality: Draft (default), Final.
   - Continuity (video only): Chain (default), Board, Recall.
   Then the style (video and pictures only): preset_search "art-styles" and ask with "question", up to four of them,
   realistic first. Keep the pick's words word for word at /s2v/setup/style; no answer: realistic. Keep every answer
   at /s2v/setup.
3. Workflows. When the chat is pinned to workflows, use those. Otherwise video is H3 Chunk (4–15 s a clip, up to 6
   shots, 480p or 768p) and pictures an image workflow that takes reference pictures. H3 has no extension from a clip:
   Chain starts each clip on the last frame of the one before (continuity-chain); Board and Recall work as they are.
   1080p or 4K is an upscale after the cut, when the upscale workflow is listed; say so when asked.
4. Assets (video and pictures). An idea or a brief first becomes a story: director with only the story to write
   (its stills-free, camera-free prose), kept as /s2v/input/script, so the sheets cover everyone in it. Then
   asset-designer on /s2v/input/script with the style; it asks the references question and keeps the sheets in
   NeuralCore (looks as "Maya - torn sleeve", times of day as "Kitchen - night").
5. Direct: director on /s2v/input/script with the style, the shape, the runtime (audio input), the cast from /cast and
   what it is for: video (clips of up to 15 s for H3), pictures (one still per shot) or a detailed script (the story
   in prose: it ends here; give the text in "reply").
6. Make it.
   - Pictures: one step per frame of the director's, all of a scene in one plan: its description, then the style
     word for word; the sheets its cast names (in the looks named) as references; the shape from /s2v/setup.
   - Video, clip by clip from clip 1, one H3 Chunk step each, from /clips/<n>:
     - Continuity by its join and the method: Chain: "continues" carries on from the clip before (continuity-chain),
       "cut" and "new place" are normal steps. Board: continuity-board for every clip of a scene after its first.
       Recall: continuity-recall for every clip. Keep what it sets at /continuity/clips/<n>.
     - The slots: the place's sheet in the anchor (in the time of day the clip names), each person's sheet in a
       character slot in the look the clip names (at most five), props in the prop slots, the board or recall grid in
       the extra reference; a speaker's voice sample in the voice sample slot when there is one.
     - Audio input: each clip's own stretch of the master (film slice at its lines' times, "pad" 2 for a line under 2 s)
       in the voice track slot, lips following it; narrator lines are never put in a clip: they go under the cut.
     - The prompt, from the clip: its goal, the scene (layout, light, time, weather, ambience, music or none), the
       opening (or the continuity skill's), the shots (each with its size, lens, angle, action and move; who speaks
       which line and when: "character 1 speaks 'line' at 3.2–5.0 s; nobody else's lips move"), the style word for
       word then the bible's look, the end state, and the locks. H3 numbers its pictures: the anchor is <Picture 1> and
       the filled character slots follow in order; call people "character 1", "character 2" and describe them by look.
     - "save_to": "/s2v/clips/<n>", "check" what must not go wrong in it. A clip that starts on nothing of another
       (a normal step under Chain or Board) can go in the same plan as the others; one that carries on waits for it.
     - After each kept clip, before the next: under Board, its stills onto the scene's board; under Recall, its
       keyframes into the library. Chain needs nothing.
7. The cut: one "assemble" step with the kept clips in order (music only when the user wants it). Audio input: film
   film with the clips and /s2v/input/audio, so the master's own sound plays under the pictures; subtitles if asked.

State:
- /s2v/input: script, lines, runtime, audio. /s2v/setup: start, shape, output, quality, continuity, style.
- asset-designer: NeuralCore entries and /characters, /locations. director: /scenes, /direction, /clips.
- continuity: /continuity/clips/<n>, /continuity/board/<scene>, /continuity/recall/keyframes. Results: /s2v/clips/<n>.
