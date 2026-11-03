id: director
title: Directing a script into scenes and shots
version: 2
desc: Use when a script, a story or even one line ("two men fighting") must be directed: what it is about and exactly how to shoot it, scene by scene and shot by shot.
craft: true
words: \b(direct|director|directing|shot list|shot plan|break (it|this|the script) down|breakdown|coverage plan|storyboard (it|this))\b
---
Never start with shots. Find the one idea the scene is built on, direct the people, and let the camera serve both;
whatever doesn't serve the idea is cut. Plan top-down whatever the input's length (one line or a whole script): the
story (what it is about, each scene's job, where the biggest turn falls), then each scene (1–3 below), then its shots
(4–6), then the words (7). A small input only makes each level short.

1. Read the whole script first, and keep the state, so every tab and every later message works from the same plan
   (read it first; write it as you go):
   - /source/script: the script word for word (read_text with "path"). A script keeps its story, events and lines
     exactly. A bare line ("two men fighting") gets the world it needs (place, how the people look, the rules of their
     world), each a stated choice; its event lands at full size and plays to its physical end; a few spoken lines only
     if needed, marked invented.
   - /style/description: the look in one line (style, palette, light). A look every module shares goes into NeuralCore
     as a style entry (book_save). Lens, angle, move and light work in every style; a camera body, film stock and grain
     only in realistic.
   - The bible, once per script and before any scene: /characters/<name>/description and /locations/<name>/description,
     one fixed description each, the words every prompt repeats. Take it from NeuralCore first (/cast: say so,
     "NeuralCore: Maya"), word for word as its pictures show it, and let the text fill only what they don't: one
     spelling of each name, age, look and outfit in every state they appear in (clean, then soaked, torn, bloodied: a
     state that recurs is a look in NeuralCore, "Maya - torn sleeve", with "from_scene"); a creature's size against a
     person and its countable parts (four wings, three eyes); each place with its light and time of day (a time of day
     that recurs is "Kitchen - night"), and its "palette" word for word; the world's rules that change what we see.
   - A location's picture: read its layout first (ways in and out, what stands where, the depth, the light sources) and
     stage every move against named things in it; nothing in a shot contradicts it unless marked invented.
   - /scenes/<n>: {"summary", "location", "type", "idea", "want", "beats", "turn", "eyes", "withheld"}:
     - want: "[who] wants [what] from [whom], blocked by [what]", and the pressure from outside the frame (a deadline,
       someone elsewhere), shown at least once;
     - beats: 3–6 changes of tactic, each a verb (to corner, bait, beg, give up), never an adjective;
     - turn: the moment power or knowledge flips, best through what the other side does, with the opposite feeling
       just before it; after it, one consequence beat (a flight, a second turn), never a stop on the flip;
     - eyes: whose scene it is (their reactions get the close-ups, and at least one true point-of-view shot);
     - withheld: what the audience doesn't see until the turn, and whether it knows more than the character
       (suspense) or less (surprise).
2. The idea: one sentence per scene, "This scene is shot as ___.", the bold specific choice that makes it unmistakable
   ("one sideways take that never cuts away from the beating", "two men who never share a frame", "glances that keep
   missing"). Draft two or three different ones (one take, cut-driven, built on what's withheld, carried by a
   performance) and keep the boldest that fits. Every later choice serves it or is cut: a bolted-camera idea has no
   handheld shot. Prefer plain behaviour (a look, a careless act) over a designed device.
3. People first. The turn is carried by what someone does, at full size, as one honest reaction (a laugh at the
   blows, a collapse, a refusal), sized to the stakes; everyone present is alive (a listening face, a shift of
   weight). Camera and props support it, never replace it.
   Scene presets hold the genre craft: when the scene is a conversation, romance, confrontation, fight, chase,
   suspense, horror, comedy, reveal, triumph, grief, montage, introduction or performance, run preset_search with its
   name alone and read it; most scenes mix two or more, so read each that fits. Take only what serves the idea.
4. Camera grammar, every choice for a reason (search presets for the words to paste):
   - Size is importance: the biggest thing in frame matters most now; save the tightest shot for the turn.
   - Angle is power: shift it as power shifts, level when nobody wins, a tilted frame only once someone's world breaks.
   - Lens: name the focal length. 18–28mm close is inside it, pressure; 35–50mm is present, honest; 85–135mm is
     isolated, watched, compressed. f/1.4–2.8 cuts the face out of the world; f/8–11 keeps the world in the story.
   - The move picks the rig, one per shot: locked off = trapped or watched; dolly or slider = a controlled push or pull;
     Steadicam or gimbal = travelling with someone; handheld = inside the panic; crane or drone = the world's scale.
     A push-in means it lands, a pull-out means isolation; never move by default.
   - Composition: doors and windows trap; empty space sits where danger will come from; symmetry is order, broken at
     the rupture; stage in depth so actors change the shot size without a cut. Keep the 180° line, and cross it on
     purpose when the relationship flips.
   - Light only from sources the scene has, one main source. Sound: silence or one rising sound before an impact,
     offscreen sound to widen the world, the ambience named so the model invents no music.
   - Rhythm: shots shorten, or time stretches, as tension builds.
5. Cuts. First weigh one take that moves with the character; about 6 shots in 30 s is a ceiling, not a target. Every
   cut has a reason: a look (cut to what they see), a reaction (in dialogue, to the listener), an action (mid-move), a
   reveal, the turn (go tighter), a place, or a stale shot. Never for a new line alone or a set length. To the same
   subject, change the size and move at least 30°, or it reads as a jump. A held take is written in timed slots
   (0–3 s, 3–6 s), one change each.
6. Fit it to the video model:
   - A clip is one generation: H3 Chunk takes 4–15 s, up to 6 shots, a keyframe per shot for frame-exact cuts. Fill a
     clip with consecutive beats in one place up to that; a change of place starts a new clip; a beat that runs past
     it splits at a cut and continues from the last frame.
   - Timing: a beat lasts as long as its words take (voiceover about 130 words a minute, about 2.5 words a second for
     dialogue, plus a second) or its action takes; shots run 2–5 s, longer when the moment needs it. A transcript sets
     the times instead (timing): a cut lands on a line's start, a clip break between lines.
   - Each shot: one size, one lens, one move with its end state, one main action. Slow weighted movement renders
     cleanly; fast tangled contact and stacked moves warp. Physical verbs with outcomes ("knuckles whiten on the
     glass"), never mood words.
   - /direction/<n>/<shot>: {"what", "who", "size", "angle", "move", "lens", "why", "cut"}: "why" is required (a move or
     an angle without a reason is left out); "cut" is its reason in one word (look, reaction, action, reveal, turn,
     place, stale).
7. Write each clip as a book, present tense, in the script's language, dialogue word for word: each beat a paragraph,
   each new shot starting "Cut to (<reason>)", the camera inside the sentences ("We open low in the mud on a 24mm,
   locked off, f/8, rain hammering the roof. Cut to (reveal) an extreme wide on a 50mm: lightning splits the clouds").
   A scene opens on place, time, weather, the main light and who is there; a person's look is given the first time
   they appear, then only what changed. A thought or memory becomes behaviour, a short flashback or voiceover.
   Keep each clip at /clips/<n>: {"scene", "time", "join" (continues | cut | new place), "goal", "cast" (NeuralCore
   names with the look worn: "Maya - torn sleeve · Kitchen - night"), "scene_state", "opening", "voiceover", "shots"
   (the book), "end_state", "locks"}. The shot's step prompt is built from it.
   For stills only: one frame per shot ({"image_description", "cast"}, the exact frozen moment at the peak of the
   action). For a story only: plain prose, past tense, no camera words.
8. Simplify before showing it: cut an extra device, a tidy payoff, a shot after the scene has landed, coverage for its
   own sake, subtext said aloud. Leave something open. Never cut the description: first looks, the place and its light
   stay.
9. Show the plan to the user as a short table (scene, shot, what, size and move, why) with each scene's idea in one
   line, and ask with "question" whether to make it: "Make these shots" or "Change something". Nothing is generated
   before that.
10. When they say go, plan the steps of the first scene from /direction and /clips (at most twelve), each with
    "save_to": "/videos/<scene>_<shot>", "check" naming what must not go wrong in it, the camera fields filled from the
    plan, the cast's NeuralCore entries (the look the clip names) and the prompt in the studio's prompt structure.
    Shots in the same place chain.
11. After each scene is made, read the reviews; a shot that failed is retaken with a changed approach, not only new
    words. Then plan the next scene, carrying on from what was really made (read /videos/...).
12. At the end, one "assemble" step puts the kept takes in order with music.
