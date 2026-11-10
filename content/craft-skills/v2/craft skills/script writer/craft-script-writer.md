---
name: craft-script-writer
label: Craft Script Writer
user_description: Turn an idea, brief or script into a detailed narrated story
description: "Use when an idea, a brief, a broken or partial script, or a full script needs to become a detailed narrator story, an audio-series episode: past-tense narration that talks to the listener, dialogue inline, every scene played out in full, each episode ending on a hook. Craft skill: works inside any workflow. Never triggers on its own: load only when the user or another skill explicitly calls for it."
command: false
---

# Script Writer

Takes whatever it is given and returns one thing: a detailed story told by a narrator, written to be read aloud as an episode. No shots, camera, clips, prompts or sheets.

**Inputs** (never ask for one):
- `script`: an idea (even one line), a brief, a broken or partial script, or a full script. Required.
- `runtime`: how long the story runs read aloud (e.g. 8 min), at about 140 words a minute; land within 10%. Missing: a script keeps its own scope; an idea or brief becomes one episode of about 1,200 words.
- `characters`, `locations`, `props`: images, when given. Describe each one as its image shows it.

## 1. Read what you're given
- **Idea or brief:** build the story it promises: the lead, what they want, who stands in the way, the world and its rules, the turn. Invent names, places and stakes; take genre and tone from the input.
- **Broken or partial script:** keep everything it has (events, lines, names, order) and repair the rest: fill the gaps, fix what contradicts itself, finish scenes that stop short.
- **Full script:** keep every event, line and name, in order, dialogue word for word. Only the narration around them is yours.
- Never drop or compress what the input names: every event, detail and repeat gets its moment.
- Write in the input's language.

## 2. Plan
- **The piece:** what it's about, whose eyes we're in, the biggest turn and where it falls, the hook it ends on.
- **Each scene:** who wants what from whom, what blocks them, and the moment it flips, best through what the other side does. Put the opposite feeling just before the flip (calm before the blow, hope before the refusal), then play one consequence beat after it.
- **Scene craft:** name each scene's kind — awakening, backstory, battle, chase, comedy, confrontation, conversation, decision, fight, flashback, grief, horror, humiliation, introduction, jealousy, montage, performance, reveal, romance, status, suspense, trial, triumph (a comeback or reversal is humiliation) — and before writing, read each kind's notes: one `preset_search` per kind, `query: "scene-<kind>"`, `categories: ["scene-recipes"]`, all in one round. They are options, not a checklist.
- **What the listener knows:** let them know what the lead doesn't (the husband's hidden fortune, the guest's real name). It keeps them leaning in.
- **Plants:** list every small thing the story will lean on later (an object, a wound, a habit, a skill, a fact, a sound) and the scene where it's first shown, before it matters.
- **Stakes:** size the reaction to the moment. A humiliation stings in public, bad news floors someone; nobody stays safely composed.

## 3. Write it as a narrated episode
- Third person, past tense, one narrator who talks to the listener: asides (*Of course, anyone who lives here knows what Brookfield traffic is like.*), questions (*But the big question was, what was Sophie even doing at the courthouse?*), teases (*She figured that was it. But she couldn't have been more wrong.*).
- Open on a moment already moving: the weather, the place, the lead doing something. Backstory comes after the hook, as a memory (*Her mind started to drift, playing back the last two months.*).
- Play every scene happening now in full: the arrival, what's said, what's done, the reaction, what it left. Never summarise it ("they argued"). Backstory and earlier events may pass in a few lines, as a memory or the narrator's summary.
- Make each rule of the world clear the first time it matters, through what happens and the lead's reaction: *The piece in his hand was gone; only what was strapped to his body had come with him.*
- Dialogue inline with who speaks and how: *"Mister Grant," she said firmly.* Thoughts in quotes: *She thought, "What if I was too late?"*
- The narrator says what people feel and why, and the body shows it: *Her legs were trembling.* *Sophie's eyes went wide.*
- Give each place its senses: *The shop smelled like old paper, and a small bell chimed whenever the door opened.*
- A one-line paragraph only for a real hit, a few per episode: *She'd fainted.*
- A person's first appearance weaves in their age, look and outfit as they act. One spelling per name.
- **Account for every object and body, every time.** Each line will be drawn as pictures, so nothing may appear, vanish or move unless the story says how. Keep track, for each person, of what is in each hand, what they carry (bag, box, phone, weapon), what they wear and its state, and where they are.
  - **Hands:** before any action that needs free hands (climbing, a door, a hug, a fight, a phone call, driving, writing), say what happens to what they hold: *She pushed the box deep into her satchel, pulled the strap tight and started up the ladder.* When it comes back, say how: *At the top, she fished the box out again.* Set down, dropped, handed over, pocketed or lost: say so, and it stays there until someone moves it.
  - **Look:** say every change the moment it happens, and it holds until the story changes it back: soaked, torn, muddy, a cut that bleeds, a coat off, hair let down, shoes kicked off, a new dress.
  - **Place and body:** say how people get from one spot to the next (stood up, crossed to the window, came down the stairs) and how doors, curtains and lights are left.
  - Each new scene picks up where the last left everyone and everything; if time has passed, say what changed.
  - Weave these into the action in the same plain voice, never as a list.
- **Small details that mean something get their own line.** Anything that counts later (a scar, a ring, a loose step, a phone at three percent, a key in a coat pocket, a name on a letter) is shown plainly the first time it's on scene and stays true until it pays off. Small things that carry meaning now (a hand that shakes, a photo turned face down, a ring slipped off) are said, not skipped.
- **Physics is real.** Weight, effort and cause and effect hold every time: a heavy trunk takes two hands and strains the arms; a fall lands somewhere and hurts; rain soaks and drips; fire smokes and burns what it touches; glass breaks into pieces that stay on the floor; running leaves people breathless; a locked door has to be opened before anyone goes through; nobody crosses a room or a city in no time. Say the steps between start and result: how she got the window open, how he got down off the roof. Only the world's own rules (magic, a power) bend this, and then the story says how.
  - **Size and fit:** say how big a thing is when it matters, and keep it that size next to people. A box goes only into a bag big enough to take it.
  - **Grip:** two hands hold two things at most. Say how each is held (by the handle, under the arm, on the hip); nobody juggles a phone and a box and opens a door at once.
  - **Clothes and body:** what they wear changes how they move: a long gown slows her on the stairs, heels slip on ice. Someone lying down gets up before they run.
  - **Marks stay:** spills spread, footprints stay in mud and snow, cloth tears, wood splinters, metal dents.
  - **Light in the dark:** every dark scene names its light (a candle, a phone torch, moonlight through a window); only what it lights can be seen.
  - **Sound has range:** a whisper doesn't carry across a hall; a gunshot turns every head.
- **Who knows what.** A character acts only on what they've seen, heard or been told in the story. Nobody uses a name before learning it or knows what happened while they were out of the room. If they learn it offstage, say how: *Her sister had texted her the whole thing on the way over.*
- **Time and light.** Each scene says the time of day, the weather and how long since the last scene. They hold until the story moves them on: night stays night, rain falls until it stops, and wounds, bruises and tiredness match the time that has passed.
- **Who is in the room.** Know everyone present in each scene and say when anyone arrives or leaves. Nobody speaks after leaving or turns up unannounced; three guards stay three until one is dealt with.
- **Fixed places.** The first description of a place sets its layout (where the door, the stairs, the windows are). It stays that way, including when the story comes back to it.
- **Skills and limits.** Nobody suddenly drives, fights, picks a lock or speaks a language unless the story showed it earlier (list it with the plants). Injuries and exhaustion carry forward: a sprained ankle still limps the next scene.
- **Every choice has a reason.** When someone does something surprising, the listener can see why. Nobody acts foolishly just because the plot needs it.
- Write for the ear: plain words, short sentences, abbreviations as said (S U V, six A M).
- **No machine-written prose.**
  - Never these phrases or their cousins: a breath she didn't know she was holding, something shifted, the air was thick with tension, time seemed to stop, a mix of X and Y, little did she know, a testament to, electricity between them, orbs, smirked.
  - Names fit the setting and culture; never stock fantasy names (Elara, Kael, Lyra, Seraphina, Thorne, Vex).
  - No "not X, but Y", no lists of three for rhythm, no paragraph that ends on a little moral.
  - Concrete, never abstract: "the room was beautiful" or "energy surged" can't be drawn. Say what is seen.
  - Each person talks their own way. Nobody explains their own feelings in tidy sentences; no therapy-speak.
  - Vary the gestures (no run of nods, sighs, clenched jaws) and the scene openings (not always the weather).
  - Feelings take time: anger or grief doesn't clear two lines after it lands.
- End on a hook: a question opened, a threat arriving, a line that lands with no answer yet.

## 4. Output
`Ep N - <title>` on the first line, then the story as plain paragraphs: no headings, scene numbers or notes. A paragraph holds one moment, its sentences running on together on the same line; start a new one when the moment, the place or the speaker changes. One blank line between paragraphs and nowhere else: never a blank line after every sentence. One episode unless the input already spans several or the runtime runs past about 10 min; then split at the strongest hooks, each episode with its own title line and ending on a hook. Post it in the chat as one fenced code block (saving it to state is not posting it), and save the same text at `/script/story`.

Before finishing, check: every event, line and name from the input is there; no scene happening now is summarised; every rule of the world is clear; read it once more following each person's hands, carried objects, clothes and position line by line: nothing appears, vanishes, changes hands or changes look without a line saying how; every plant is shown before it pays off; every action is physically possible, step by step (sizes, grips, clothes, marks, light, sound); nobody knows what they couldn't; time, weather, who's present and each place's layout hold; no skill is used before it's shown; every surprising choice has a visible reason; no banned phrase, stock name or abstract line is left; the runtime is within 10% when one was given; the ending hooks.

## State
```
/script/story     the whole text, word for word as written
```
