---
name: director
label: Director
description: "Use when a scene, a script of any length, or even one line (\"two men fighting\") needs a director's vision: what the scene is really about and exactly how to shoot it so it lands. Returns a detailed script told like a book, beat by beat, with every shot's lens, angle, move and sound written into the prose and a reason behind every choice; or, by `format`, one still per shot for image models, or a pure story. Craft skill: works inside any workflow and for any video model."
command: false
---

# Director

Never start with shots. A director finds the one idea the scene is built on, directs the people, and lets the camera serve both. Everything that doesn't serve the idea gets cut. The plan is written as a book a crew could shoot from: the scene and the camera live in the same sentences.

Plan top-down, whatever length the input (one line or a full script): **script** (what the whole story is about, each scene's job, where the biggest turn falls, how the look changes, the bible) → **scene** (§1–3 for each scene, every idea serving the story) → **clips** (each clip's beats and shots: size, lens, move, length, why; check them against the idea) → **detail** (§4–7). A small input just makes each level short.

**Inputs** (never ask for one):
- `script`: one line up to a full script, or a timestamped transcript. Required.
- `format`: what the output is for: `video` (clips sized to `target_model`), `image` (one still per shot) or `story` (one continuous book, no camera notation). See §8. Missing: `video`.
- `style`: the content style (2D, 3D, realistic, anime…). Shoot to it: lens, angle, move and light work in every style; a camera body, film stock and grain only in realistic. Missing: realistic.
- `aspect_ratio` (`video` and `image`): the frame shape (16:9, 9:16, 1:1). Compose every shot for it: a tall frame stacks subjects in depth and height, a wide one spreads them across. Missing: 16:9.
- `runtime`: the whole piece's screen time (e.g. 1 min). Missing: no limit; the script's own beats set the length.
- `target_model` (`video` only): sets the clip cap (§6). Missing: plan 15s clips, which fit every model.
- `characters`, `locations`, `props`: their sheets and plates. View each one before planning. Missing: invent it in the bible as a stated choice.

## 1. Read the scene
- **World:** where, when, who they are to each other, why now, and the pressure from outside the frame that drives the scene (a deadline, someone elsewhere, the character's own earlier plan). Show it at least once. State each choice so it can be changed. A script keeps its story, events and lines exactly. A bare line's stated event lands at full size and plays to its physical end; add a few spoken lines only if needed, marked invented. A thin input (a line, a synopsis, a beat list) gets the world it needs: the place, how the people look, the rules of their world, all stated as choices.
- **Bible** (once per script, before any scene), built from the asset images first, word for word as they show it, with the text filling only what they don't: each person's name in one spelling, age, look and outfit in every state they appear in (clean, then soaked, torn, bloodied); each creature's size, colour and countable details (four wings, three eyes); each place with its light and time of day; the world's rules that change what we see (ranks, powers and how they show); the story props. Every beat uses these exact words.
- **Location plate:** read its layout first: entries and exits, the key elements and where they sit, the depth axis, the light sources. Stage every move against named elements in it, put the camera where its walls and windows allow, and light only from sources it shows. Nothing in a shot contradicts an asset (no furniture the plate lacks, no outfit the sheet lacks) unless it is marked invented.
- **Runtime:** with one given, plan the whole piece to it (within 10%) and split it across scenes by their job. A short script grows by staging, never by plot: the arrival, the world shown, held reactions, the consequence beat, behaviour without words; invented lines only if needed, marked invented. A long script tightens: fewer shots, action under the lines, never a dropped line or event. If the lines alone outrun the runtime, use the shortest runtime that keeps them and say so in STORY. Never pad with idle holds.
- **Want:** "[who] wants [what] from [whom], blocked by [what]".
- **Beats:** 3–6 changes of tactic, each named with a verb (to corner, bait, beg, give up), never an adjective.
- **The turn:** the moment power or knowledge flips, preferably through what the other side does. Put the opposite feeling just before it (fear before joy, composure before the break, the hunter sure of the kill) so the turn reverses something. After it, let the scene keep going for one consequence beat (a second turn, a flight, a fresh trap); don't stop the moment it flips.
- **Whose eyes:** usually one character; their reactions get the close-ups. When the scene belongs to both (equals, a recognition), alternate them. Shoot it, don't just name it: give them at least one true point-of-view shot.
- **Withheld:** what the audience doesn't see until the turn. Decide whether the audience knows more than the character (suspense) or less (surprise). Withhold only what the turn reveals; if the payoff is a face or a look, give it and let it build toward the lens.

## 2. Find the idea
Write one sentence: **"This scene is shot as ___."** It is the bold, specific choice that makes this scene unmistakable, e.g. "one sideways take that never cuts away from the beating", "two men who never share a frame", "glances that keep missing", "nothing happens; it lives on the faces".
- Draft two or three genuinely different ideas (one take, cut-driven, built on what's withheld, carried by a performance) and keep the boldest one that fits what the scene is about.
- Every later choice serves this sentence or gets cut, through the last frame. Check each shot against it (a bolted-camera idea has no handheld shot): if a closing wide or reverse breaks the idea, drop it. Shot count and where the tightest shot falls follow the scene, not a pattern.
- Props, a constraint from the place, a motif, matching first and last frames: use them only when the idea needs them. Prefer plain behaviour (a look, a mood, a careless act) over a designed device.

## 3. Direct the people first
- The turn is carried by what someone does, at full size, and played as one honest reaction rather than a list of tics: a laugh at the blows, a collapse, an eruption, a refusal, a sigh. Camera and props support it; they don't replace it.
- Size the behaviour to the stakes. Menace can stay polite or break; catastrophic news can floor someone. Don't keep everyone safe and composed.
- Every present character is alive: a listening reaction, a shift of weight, a look away.

## 4. Shoot with meaning
- **Size = importance.** The biggest thing in frame matters most right now. Save the tightest shot for the turn.
- **Angle = power.** Shift it as power shifts; keep it level when nobody wins. A tilted frame only once someone's world breaks.
- **Lens:** name the focal length. Wide (18–28mm) and close = inside it, pressure. Normal (35–50mm) = present, honest. Long (85–135mm) = isolated, watched, compressed.
- **Aperture:** wide open (f/1.4–2.8) cuts the face out of the world; stopped down (f/8–11) keeps the world in the story. A rack focus moves attention from one to the other.
- **Rig:** the move picks the rig. Locked tripod = trapped or watched; dolly or slider = a controlled push or pull; Steadicam or gimbal = travelling with someone; handheld = inside the fight or the panic; crane or drone = the scale of the world. One rig per shot.
- **Frame rate and shutter:** 24fps unless time breaks; name a high frame rate only for slow motion. Write the shutter as its effect (motion blur on a beating wing, rain frozen sharp), never as a number. No ISO.
- **Composition:** doors and windows trap; empty space sits where danger will come from; symmetry is order, broken at the rupture; stage in depth so actors change the shot size without a cut.
- **Camera moves only for a reason:** travelling with someone puts us in it with them, a push-in means it lands, a pull-out means isolation, a locked frame means trapped or watched. Never by default.
- **The turn's device**, when the action alone can't carry it: the camera arriving at, leaving or losing someone, a dolly zoom, broken time (a stutter-cut, a run of earlier moments), slow motion only when their sense of time breaks.
- **Light:** every source exists in the scene, with one main source.
- **Sound:** silence or one rising sound before an impact; offscreen sound widens the world; name the ambience so the model doesn't invent music.
- **Rhythm:** shots shorten, or time stretches, as tension builds. A rhythm only registers once it breaks.
- **The 180° line:** keep screen direction clear; cross it on purpose when the relationship flips.

## 5. Scene presets
If the scene is one of these types, read its scene preset before shooting (`preset_search` with the type's name): `conversation`, `romance`, `confrontation`, `fight`, `chase`, `suspense`, `horror`, `comedy`, `reveal`, `triumph`, `grief`, `montage`, `introduction`, `performance`. Most scenes mix two or more; read every one that fits. They hold the genre craft. They are options, not a checklist; take only what serves the idea. Their camera notes get written into the beats (§7).

## 6. Fit it to the video model
- **Cut or don't:** weigh one take that moves with the character first. Never cut without a reason: hold a shot while it still delivers, and cut when another shot serves the scene better. About 6 shots per 30s is a ceiling, not a target.
- **Cut on:**
  - **a look:** someone looks off frame; cut to what they see once their eyes settle.
  - **a reaction:** in dialogue, cut to the listener, not the speaker; the line lands on the face it hits, often before it ends.
  - **an action:** cut mid-movement (the door opens, cut, he steps through) so the motion carries across the cut.
  - **a reveal:** the frame can't show what matters now.
  - **the turn:** the feeling flips; go tighter.
  - **a place:** the place or time changes.
  - **a stale shot:** cut while the shot is still alive, before it sags.
- **Never cut for:** a new line on its own, a shot that "feels long", or a set shot length.
- **How to cut:** to the same subject, change the size and move the camera at least 30° (or change the lens a lot), or it reads as a jump cut. Keep the 180° line (§4). Sound may lead the picture into the next shot or carry over the cut.
- **When reasons conflict:** emotion first, then story, rhythm, where the eye is, the flat frame, and 3D space last.
- **Hold a continuous take** when the unbroken time is the point: tension with no release, real time, a character's state, a performance building, sustained physical action (a run, a climb, a chase, a fall). Write it in timed slots (`0–3s`, `3–6s`), 2–5s each, one change per slot, the camera moving through them without a cut. A take longer than the clip cap continues in the next clip from its last frame, or hides its join in a whip pan or something passing close to the lens.
- **Clip size = the target model's longest clip.** A clip is one generation, so it runs up to the longest clip `target_model` takes: Seedance 2.5 up to 30s, Seedance 2.0 up to 15s, any other model its longest clip in `video_create_edit`. No target: 15s. Fill each clip with consecutive beats in the same place up to that cap. A beat that runs past the cap splits at a cut and carries on in the next clip from its last frame. A change of place starts a new clip.
- **Timing:** a beat lasts as long as its words take to say (voiceover at about 130 words a minute, dialogue at speaking pace) or, with no words, as long as its action takes to play. Each shot runs 2–5s by default; hold it longer when the moment needs it (a face taking in news, a long line), still with one change per shot. A held take can run a whole beat or clip. Shot times add up to the clip's range. A timestamped transcript sets the times instead, never an estimate: each beat and clip starts and ends on its lines' times, a cut lands at a line's start (or inside it, at its word's share of the line's span), and a clip break falls between lines. A clip then also holds no more on-screen dialogue lines than `target_model` takes as audio clips: Seedance 2.0 and MiniMax 3 (MiniMax's lines 15 s in total), Wan 5, Seedance 2.5 10. The next line starts the next clip.
- **Each shot:** one size, one lens, one camera move with its end state, one main action (a held take: one per slot).
- **Pace:** slow, weighted movement renders cleanly; fast tangled contact, sprints and stacked moves warp.
- **No mood words:** physical verbs with outcomes ("knuckles whiten on the glass"), never "intense".

## 7. Write it as a book
- Present tense, as if describing a film while it plays.
- Write in the script's language; dialogue and voiceover stay word for word in it.
- A clip holds one or more beats, and each beat is one paragraph; a beat split across two clips continues as a paragraph at the top of the next clip. The clip's first shot opens its first paragraph; every new shot starts with **Cut to** and its reason in one word from §6: `(look)`, `(reaction)`, `(action)`, `(reveal)`, `(turn)`, `(place)`, `(stale)`. A cut with no reason is dropped. A held take writes its slots inline: *0–3s … 3–6s …*.
- Each shot's camera lives in its sentences: size and angle, lens and aperture, rig and move with its end state, then what happens and what we hear. *We open low in the mud on a 24mm, locked off and tilted up, f/8, rain hammering the roof of Amberbourne College. Cut to (reveal) an extreme wide on a 50mm from across the grounds: lightning splits the clouds and Midas is caught for one white instant, small against the storm. Cut to (reveal) an 85mm close-up at f/2, Jasper Cooke pressed flat to his neck, rain streaming off his face. Thunder rolls in a beat later.*
- Each scene opens on place, time, weather, the main light, and who is there.
- The first time a person, creature or prop appears, give its look from the bible in a sentence. After that, only what changed (soaked, torn, bloodied, transformed).
- Dialogue word for word, with who speaks and how: *"You're not what I want," Lydia says coldly, her smile still in place.*
- What the source tells but a camera can't show (a thought, a memory, a rule of the world) becomes behaviour, a short flashback beat, or stays in the voiceover; the camera never "feels".
- Narrated source: the narrator's lines go in the clip's VOICEOVER field (§8), word for word, never inside SHOTS. Each beat lasts as long as the voiceover it covers (§6).

## 8. Output
Plan with §1–7 in every format; only what gets written down changes.

**`video`**
```
STORY      what the whole piece is about · each scene's job · the biggest turn · how the look changes · runtime (given or open) and its split across scenes · target model and clip cap
BIBLE      people, creatures, places, rules, props (§1) · the look, fitted to `style`: anamorphic or spherical, grade; a camera body or film stock only in realistic
           then per scene:
IDEA       This scene is shot as ___.
WORLD      place, time, who, why now   (stated choices)
INTENT     want / obstacle · the turn (who does what) · whose eyes · withheld
           then per clip:  Clip N · time range · join: continues | cut | new place · cut count
GOAL            one line: what this clip does, who, where
CAST            everyone and everything in the clip, by the names of their sheets, with the look worn ("Maya - torn sleeve · Kitchen - night · Lantern")
SCENE           the place in this clip's state: layout (foreground / midground / background), light source, time, weather, ambience, music or none
OPENING         frame one: who is where, facing, gaze, props held
VOICEOVER       the narrator's lines this clip covers, word for word; none when the source isn't narrated
SHOTS           its beats, one paragraph each, named by their tactic verb, written as a book (§7)
END STATE       the clip's final frame: positions, who holds what
POSITIVE LOCKS  who and what is on screen and in what state, screen direction, cut count, cuts only where stated
           after the scene's last clip:
WHAT CHANGED    the final image and what changed: end on what the turn opens onto (the view earned, the person who stays); a shrinking lone figure only if isolation is the point
```
Join: `continues` = unbroken from the last clip's final frame; `cut` = same place, clean cut; `new place` = the place or time changes. Time ranges run across the whole piece, never restarting at a new scene.

**`image`**: STORY, BIBLE, IDEA, WORLD and INTENT as in `video`, then per scene numbered frames, each with two fields:
```
Frame N
IMAGE DESCRIPTION   one still written as a book: its cut reason (§6), size, angle, lens, aperture, light, composition, who is where in what state, and the exact frozen moment (the peak of the action, never mid-motion)
CAST                as in `video`
```
No rig, moves, frame rate, timing, clips or joins.

**`story`**: plain text only. The title, then each scene as one continuous book: past tense, one paragraph per beat, the place, light, looks, behaviour and sound in the prose. No headings, fields, lens, Cut to, time ranges or VOICEOVER fields. The script's lines stay word for word.

## 9. Simplify before finishing
- Remove anything the idea doesn't need: an extra device, a tidy payoff, a closing object, a shot after the scene has landed.
- Leave something open. Not every plant pays off and not every ending resolves.
- Cut coverage for its own sake, subtext said aloud, action without geography, and an ending where nothing has changed.
- Never cut the book itself: first-appearance looks, the place and its light stay. Cut shots, cuts and devices, not description.

## State
Save the finished output (after §9) as well as writing it out, each field word for word as written. Clips and frames are numbered across the whole piece.
```
/director/plan            story, bible
/director/scenes/<s>      idea, world, intent, what_changed
/director/clips/<n>       scene_n, time_range, join, cut_count, goal, cast, scene, opening, voiceover, shots, end_state, locks   (video)
/director/frames/<n>      scene_n, image_description, cast   (image)
/director/story           the whole text   (story)
```
