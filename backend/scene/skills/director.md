id: director
title: Craft Director
version: 3
desc: Plan every shot of a story before anything is generated
description: Use when a story or script must be planned into shots before generation: episode, then scenes with a type and its camera grammar, then beats, then every shot's picture, who is in frame, motion, move, angle, size and length. Craft skill: works inside any workflow and for any video or image model. Never triggers on its own: load only when the user or another skill explicitly calls for it.
craft: true
words: \b(direct|director|directing|shot list|shot plan|break (it|this|the script) down|breakdown|coverage plan|storyboard (it|this))\b
---
# Director

Top down: episode → scenes → beats → shots. Save the episode and the scene list first, then plan each scene's beats and shots in its own round, saving as you go; each level is built only from the level above. The story is locked; the plan decides only what is seen. Never call `creative_direction_guide`: the plan is written by you, here.

**Inputs** (never ask for one):
- `story`: the story or script, or its state path. Required.
- `characters`, `locations`, `props`: their sheet paths, each with its saved look, layout and palette. Positions, entrances and angles use only what each location has. **Studio:** the sheets are NeuralCore entries (/cast: each with its "visual", looks, palette and relatives), or the paths craft-asset-designer kept.
- `style`: the style prompt. Missing: realistic.
- `aspect_ratio`: Missing: 16:9.

## 1. Episode
From the whole story:
- **Story** — one line: who wants what (or whom), what stands in the way, what has changed by the end.
- **Arc** — scene by scene, the viewer's feeling (e.g. humiliation → heat → hurt → hope → hook).
- **Leads** — who holds the power at the start; each lead's tell: one small physical giveaway of what they hide (a jaw tightening, a hand closing, eyes dropping to the lips), an insert whenever the feeling leaks.
- **World** — who has the money, rank or power and where each lead stands in it; the rival and the secret that can blow it open; any magic or power, what it looks like (where on the body or world it shows, its colour, texture, how its light behaves) and what sets it off; the cast, key locations and the motif as their sheets show them, and any look that changes for good with the shot it changes on. Every recurring element — a look, the motif, a power, a car — has one fixed description, repeated word for word in every shot that shows it. Money, rank and power show through things and bodies, never a caption: wardrobe, cars, rooms, staff, who sits and who stands.
- **Style** — the `style` input. On realistic, every shot is written as if filmed by a real camera: real skin, fabric, metal and stone, real light and lens depth.
- **Era** — one era for the whole episode: the story's, else today's world, in the city and country the names and language point to. How worn or rich a place looks follows who owns it; light comes only from real sources (sun, moon, windows, lamps, candles, fire, city lights through glass, a phone screen), never neon signs or glowing strips unless the place is a club. Every place, costume, car, phone and prop belongs to it, every montage place included.
- **Opening** — the first shot hooks on the leads, already in motion; when the world is the hook, the episode's biggest image at full scale. When the story opens on something that happened (a betrayal, a death, a curse, a public humiliation), even said as a figure, the opening shows it happening, then what it left, then follows the story; never the aftermath alone.
- **Throughline** — the opening image, the closing image, and the one motif between the two, an object or a gesture from the story, that evolves between them.
- **Spend** — the hinge scenes (T3) and which scenes echo each other (see Echoes).

## 2. Scenes
A new scene starts where the story beat changes, usually every 10–30 s of screen time. A run of places or things the story lists (a tour of settings, a list of what was lost) is one montage scene, not one scene each. Per scene:
- **Type** — what the scene does to the viewer, from the table; one type, the one it ends in. Description is Status when it shows money, rank or power in action, Backstory only when it states how things stand or stood or the world's rules; the other types need a character something happens to. Status stripped before witnesses is Humiliation; one refusing the other is Rejection. Bond only when a new trust or link is made; two people coming back together is Reunion, a tender moment between them Intimacy, the hero wanting what is out of reach Longing; the almost-kiss is Pull, the kiss Surrender, sex Heat.
- **Tier** — T1 nothing changes, it could be explained away: a lighter grammar — fewer shots, a gentler camera, a small exception. T2 it lands and stays for the scene: the table as written. T3 an option is gone for good: the grammar pushed hardest. A T1 scene shot like a T3 spends the episode too early.
- **Feeling** — the viewer's feeling in → out; "in" is the previous scene's "out". Every scene opens on impact, already in motion.
- **Grammar** — height, frame, light and camera from the type. Every shot keeps them; shots vary size, angle, subject and lens inside them.
- **Exception** — exactly one shot that breaks the grammar (Status has none), on the scene's biggest beat. Micro-cuts are not exceptions.
- **Tone** — the place's real light, made dramatic by the grammar's light: one strong source, deep shadows with detail, a rim through haze or dust, soft highlights. Colours follow the place's palette from its sheet, muted and filmic; the motif's or the power's colour, when it has one, is the only saturated hue and the same everywhere. Each place keeps its palette and returns with it. Between two people, the light follows them: as they draw together it softens — a soft key, a gentle rim, the palette's warmer side; when the bond breaks it cools and hardens — deeper shadow, more empty space around them.
- **Pace** — the scene's typical hold: backstory and calm 3–5 s; tender and intimate 2.5–3.5 s; action, lists, reveals 1.5–2.5 s.
- **Build** — wide to set the place → medium for the action → close or macro on the emotion or the motif; the last shot hands off to the next scene, which opens wide unless a match cut links them (a shape, a motion or the motif carried across the cut).

**Height** under: hero lowest in frame, others tower · level · over: hero shot from below · god: above everyone, nobody's eye · flip: under turns to over, the flip is the turn.
**Frame** ring: watchers around the hero, closing · door: a threshold the camera won't cross · open: space around the hero · crowd: foreground bodies squeeze the hero · two: two figures held together · tight: both faces filling one frame · tiny: a vast wide, the hero small and still · split: two halves opposed.
**Light** one: a single warm source in the world · split: two opposing temperatures · above: high, broad, nobody's light · hero: the hero or their power is the brightest thing · rival: the threat is the light · drained: light that favours nobody.
**Camera** slow: pushes, drifts, slow orbits and cranes · fast: whips, tracking, fast orbits, FPV · handheld · lock: the camera holds, the world in frame keeps moving.

| Type — what the scene does | Height | Frame | Light | Camera | Exception shot |
|---|---|---|---|---|---|
| Meet — first sight or a collision, the spark | level | crowd, the two finding each other through it | one | slow, a push as their eyes meet | the first held look: a tight two, the room gone |
| Friction — enemies spar, heat under the insult | over, with whoever wins the line | two | split | handheld | the insult lands and the eyes drop to the lips: one locked close |
| Pull — wanting against their will, the almost-kiss | level | tight | one | slow pushes, handheld in close | the interruption: a wide that snaps them apart |
| Surrender — the kiss, the yielding | level | tight | one | slow orbit around them | one wide of the world around them |
| Heat — an intimate scene, desire acted on | over with whoever leads, else level | two, then tight; an insert of hands or fabric | one, low and dim | slow drifts and orbits; handheld in close | one wide of the place around them, the two small in it |
| Rejection — one refuses or shames the other, often before witnesses (a breakup, divorce papers, a public slap) | under: the rejected; the rejecter above | ring, the witnesses | above | fast, on the witnesses | the rejecter's crack: a close where their eyes betray them |
| Humiliation — status stripped before witnesses, no danger | under | ring, tightening | above | fast, on the mockers | the camera rises to the hero's eye level as they almost recover |
| Jealousy — a rival closes in on one of them | level | crowd, the rival between the two | rival | handheld | the two lock eyes across the room, the rival out of frame |
| Protection — one shields the other from a threat | over: the protector | two, the threat in fore- or background | rival | fast; lock as the protector stands | after the threat: the protector looks back, level, face softened |
| Confession — the feeling is said | level | two, closing in | one | slow push | the answer: one locked two-shot |
| Betrayal — an ally withdraws | level; the betrayer never from below | door | split | slow | equal-height two-shot, the last intact moment |
| False hope — a rise, then the drop | under → level → under | crowd | hero on the rise, drained after | slow | the hope as the only light, every face turned to it |
| Decision — alone, two options, one chosen | level | split | split | slow | the camera holds; the hero crosses the dividing line; it doesn't follow |
| Comeback — the one looked down on returns changed for good (a new look, a new rank, a hidden identity out) | flip | open, every head in the room turning | hero | lock at the arrival, slow after | the flip itself: the camera below the hero for the first time — spend once |
| Awakening — what the hero is changes for good | flip | open, the enclosure releases | hero | lock at the change, slow after | the flip itself: the camera below the hero for the first time — spend once |
| Bond — a new trust or link is made (a deal, a pact, a contract marriage signed, a secret shared) | level | two | one | lock | one slow push as it is accepted — betrayal's look reversed |
| Reunion — two people come back together | level | two, closing in | one | slow drift and orbit, closing the gap | the first touch, held in one locked close |
| Intimacy — a tender moment between two, nothing at stake yet | level | two | one | slow drifts, pushes and orbits; handheld in close | one locked hold on the smallest gesture |
| Longing — the hero alone, wanting what is out of reach | level | open, the hero small | one, from what they want | slow drift toward it | what they want, seen through their eyes |
| Threat — danger closes in, no answer yet | under | crowd | rival | handheld while chased, lock when cornered | a locked wide as the hero stops running |
| Trial — a formal test or reckoning, people watching (a boardroom, a court, a family council, a wedding) | god | tiny | above | slow | one shot at the hero's eye level just before the result |
| Revelation — reframes what came before | level | open | one | slow, one push onto the source | an insert repeating the reframed scene's shot exactly |
| Claim — one chooses the other before everyone | flip | crowd parting to two | hero | fast | the paired rejection's shot reproduced, outcome reversed |
| Reversal — the one shamed turns it on whoever shamed them, before witnesses | flip | ring, the witnesses turning | hero | fast | the paired rejection's or humiliation's shot reproduced, roles swapped |
| Triumph — the hero wins with what they gained | over | the paired loss's frame, inverted | hero | fast | the paired loss's shot reproduced, outcome reversed |
| Status — someone shows what money, rank or power means (a display of wealth, an order that moves a room, a power in action) | god | open | on the one showing it | fast, the camera enjoys itself | none |
| Backstory — how things stand or stood, or the world's rules (the family's history, the contract's terms, how a power works), nothing changes | level | open or two | one | slow | an insert of the document, object or record named, after its wide reveal |

The words decide every picture; the type decides only how it is shot.

**Echoes.** A claim or a reversal reuses the setups of the rejection or humiliation it pays off, outcome reversed; a triumph reuses its loss's. A surrender completes a pull's almost-kiss on its framing. A revelation repeats the exact shot it reframes. When the hero later attempts what a Status scene showed, both get identical coverage. A comeback's or awakening's new look is locked on its own look sheet and reused from then on. A type that returns at a bigger scale reuses its earlier setups, pushed further.

## 3. Beats
Split each scene's text into beats; every sentence belongs to exactly one. Per beat:
- **Mode** — *sequence*: one place, continuous time; geography, screen direction, props, wounds, looks and power state carry shot to shot. *montage*: the story summarises or lists; each line its own place or moment, everyone dressed for that place and time. *flashback*: the past told through the hero — the version where they are in frame (as a child, a witness, the one left behind), dressed for that time; at least 2 shots and 3 s. *insert*: 1–3 lines on one detail. *intercut*: two places at once; each keeps its own grammar and tone and resumes where it left off.
- **Instruction** — one line: what is visible — what it must make the viewer feel, the harder feeling first. Name the specific thing seen, never its abstraction ("the cost", "the pain"); show it through the leads, never report what others feel.

## 4. Shots
Spend the scene's shots on its strongest words — the ones that name a thing, a feeling or a turn; a shot can carry several lines. Pick the picture by what the line means (a figure of speech is pictured by the real thing it stands for, never literally: "the kingdom bleeds" is its war and its dead) and by what the line is:

| The line is | The picture |
|---|---|
| a thing or event — a place, creature, object, company, war, scandal | the thing doing what the line says about it. An event and what it left gets both, in order — the event happening, then the aftermath: a wedding called off, then the emptied hall; a plague spreading, then the empty town |
| a state or abstract line about the hero | the strongest situation that proves it, in one frame: put them against the people or world the line is about, or mark it on their body (a price paid — a slap's red mark, a ring gone from a finger, a fresh scar). Never just their face, never a metaphor |
| the first naming of a major place, family, company, being or power | its biggest image, one of the leads in it for scale |
| a list | one quick shot per item |
| a short line stating the theme | 2–3 quick cuts, fresh images of it — never an echo |
| addressed to "you" | the hero faces the lens |
| a question or mystery | the object, then the hero's reaction |
| a memory or a past moment named ("since the day they met") | that moment itself, as a flashback beat with the hero in it — never a present-day close-up |

**Dialogue.** A character's line shows its speaker mid-line, mouth moving, the body acting it (a threat leans in, a plea opens the hands). A line that lands — threat, reveal, insult, order, question — cuts to the listener's reaction before the next line. A line past ~3 s splits: speaker, then the listener or an insert of what they speak of. Two people: over-the-shoulder back and forth; the sequence fixes who stands on which side, eyelines match across cuts (one looks right, the other left), and the camera crosses that line only on a move the viewer sees. A character recounting something is seen speaking first, then what they describe.

Every shot then names:
- **Picture** — what the line calls for, the props in hand.
- **In frame** — everyone and everything the camera sees, by their sheet names, each with where they are in the place and which way they face. A shot shows only who it names: someone present but not named is not drawn, so a wide names everyone in the place.
- **Motion** — what the subject does and what the world does (rain on glass, curtains, steam, traffic, cloth, hair, embers, fog, sparks). No still frames. Every sequence but a tender or intimate one has at least one shot where someone moves through the frame and the camera moves because of them (follows, reveals, walks with them).
- **Move** — push in, pull out, orbit, crane, track, whip pan, dolly zoom, FPV fly-through, rack focus, handheld, snorricam (rigged to the body, the face locked in frame, the world swinging behind), tracking the feet at ankle height, at the scene's camera. A beat's action sets the move over the scene's camera: a landing, a run, a fall, a gust is followed by a moving camera even in a scene that locks. Never more than 2 locked shots in a row; a held shot past 4 s drifts, pushes or orbits. The camera stops only on a lock, and even a lock keeps a faint handheld sway — a breath of movement, never a dead-still frame. A romantic scene (Meet, Friction, Pull, Bond, Reunion, Intimacy, Confession, Surrender, Heat, Longing) keeps the camera calm: its type's camera is spent as one signature move, on the beat where the bond wakes or resolve breaks; every other shot is a lock or gentle handheld, mixed, and the 2-lock and 4 s drift limits don't apply. Never a descent from above onto a character (craning or pushing down to them).
- **Angle** — never a size: low, ultra-low at ground level, high, overhead, three-quarter, dutch, over the shoulder, through a foreground, a character's or creature's POV, silhouette, reflection, inside the scene's height. Dutch only for unease, threat, action and power, at least once in such a scene of 3+ shots, never in a tender one. Every action, threat or power scene of 3+ shots has one body or ground shot (snorricam, POV, the feet, ultra-low); a tender or intimate one spends it on hands, breath and fabric instead.
- **Size** — its place in the build, with a lens for the feeling: long and shallow for intimacy and closes, normal for dialogue, wide and close to the subject for spectacle, action and ground shots.
- **Length** — as long as what plays in it needs at a natural pace (a look about a second, a line at speaking pace, a walk as long as it takes), near the scene's pace, never under 1.5 s (video models merge shorter shots). Never shorten the blow or the turn; tighten the setup instead.

Compose for the `aspect_ratio`: 16:9 spreads subjects across the frame, 9:16 stacks them in depth and height, 1:1 centres the subject; build depth front to back.

Status is pushed only when the line or scene is about it, or at the peak of a Rejection, Humiliation, Status, Claim, Reversal, Comeback or Triumph. Magic and creatures appear only when the line or scene is about them, always on the hero or in a real place — through their body, their gear, a creature, the architecture — never floating in a void. A secret, a debt, a contract or a power with no body of its own is carried by one recurring object the story gives it. Every frame is cinematic: foreground, subject and a lit background with depth, never a black void; light from sources in the world through haze, rain or glass, a rim on the subject; shallow focus on closes and macros. Show the world through the recurring cast and props before inventing extras; one of the leads is in frame wherever the line allows; others are shown through what they do to the leads. No readable text in any picture: phone screens, contracts, headlines and signs show as light, layout and shapes. Never the same angle and move twice in a row (in a romantic scene, only the angle must change); at least 3 angles in a scene of 3+ shots. Neighbouring shots differ in place or framing and never morph into each other, so every cut is a visible hard cut. No picture shows what the story has not yet reached.

**Last**, mark each scene's exception and apply the echoes. They change how a picture is filmed — height, frame, light, move — never the picture the words call for; an echo shot repeats its source shot's size, angle and move word for word.

**Check each scene before saving:** every sentence in exactly one beat; every line of dialogue word for word from the story; every picture shows its words or the hero's reaction to them and serves its beat's instruction; every shot names everyone in its frame; every shot keeps the grammar except the one exception; the feeling chain holds; echoes reuse the setups they name; no filler ("epic landscape").

## State
```
/director/episode                 story, arc, leads, world, style, era, opening, throughline, hinges, echoes
/director/scenes/<n>              type, tier, feeling, grammar, exception, tone, pace, location, text
/director/scenes/<n>/beats/<b>    text, mode, instruction
/director/scenes/<n>/shots/<m>    beat, words, picture, in_frame, motion, move, angle, size, length_s, exception, echo_of
```

## Studio: on its own
Inside script-to-video, its steps make the plan into clips. When this skill runs on its own:
1. Once the plan is saved, show it to the user as a short table (scene, shot, picture, in frame, size · angle · move, length), each scene's type and tier in one line, and ask with "question" whether to make it: "Make these shots" or "Change something". Nothing is generated before that.
2. When they say go, plan the shots of the first scene (at most twelve steps), each a "generate" step with "save_to" "/videos/<scene>_<shot>", "check" naming what must not go wrong in it, the camera fields filled from the shot (shot_size, angle, move, end_state), the cast's NeuralCore entries in the looks the shot names, and the prompt in its workflow's prompt guide. Shots in the same place chain.
3. After each scene is made, read the reviews; a shot that failed is retaken with a changed approach, not only new words. Then plan the next scene, carrying on from what was really made (read /videos/...).
4. At the end, one "assemble" step puts the kept takes in order with music.
