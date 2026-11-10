id: brand-motion
title: Brand motion — logo reveals, brand reels, services explainers and launch teasers
version: 2
desc: Use for a brand's motion graphics video: a logo reveal or sting, a brand reel or sizzle, a services or product explainer, a launch teaser or promo. Built as a HyperFrames project, with stops for the user to choose the story and the look.
words: (?!)
---
A brand's motion graphics, made as a HyperFrames project you direct (load the hyperframes skill first: its contract,
its work loop, and the guides it names). The bar: an agency's work. Everything on screen is the brand's own (its mark,
its colours, its words, its real product, its photos), set in one look held from the first frame to the last, cut to
music, with sound on what moves, delivered in both shapes. The user can give anything, or almost nothing: make the
best of what there is, never invent what the brand is not, and ask only for what you cannot decide.

## The four kinds

| Kind | Length | Shape of it |
| --- | --- | --- |
| Logo reveal (sting, intro, outro) | 6–12 s | The mark is built from its own parts, the wordmark follows, the tagline last; held 2 s on the lockup |
| Brand reel (sizzle) | 25–45 s | Music-led: a cut on the beat (every beat or every two), several worlds of one look, the brand's words as kinetic type, a turn, the lockup |
| Services explainer | 35–60 s | A hook, "what we do", one scene per service (its number, its name, one line, a visual of what it does), the approach, proof, the lockup and how to reach them |
| Launch teaser (promo) | 20–35 s | The problem, the turn, the product doing what it does (its real screens or photos), proof, the date or the offer, the call to act |

A request between kinds takes the nearest; a mix (a reel that ends on the services) is fine.

## 1. What there is

Read what the user gave and NeuralCore before you ask anything: the brand's name, its logo (any file), its colours and
fonts if said, its site or a text about it, the services or product, photos, footage, screenshots, a date, an offer,
where it will be posted. A link: web_fetch for the words, import_url for the pictures. Keep it all in the run state
(/motion/brief). Ask once, in one question with buttons, only what decides the film and is nowhere: most often nothing.

Shapes: both 9:16 (1080x1920) and 16:9 (1920x1080) unless the user names one. 60 fps for a logo, a reel and a teaser;
30 for an explainer with much text.

## 2. The logo

Run the film tool's logo op on whatever logo there is (PNG, JPEG, SVG, a screenshot of it). It gives a transparent PNG
cut to the mark, the brand's colours, the ground the mark wants, and for an SVG its cleaned markup. Keep it in
NeuralCore (book_save, type style, "<Brand> logo", its colours in "value").

- An SVG: read it (read_text on the SVG item), and build the mark from its own shapes in the page: each path drawn
  (DrawSVG), assembled, or folded in, the way the brand's shapes suggest. Never change a shape.
- A PNG or a JPEG: the mark is whole; perform its arrival: a mask or a wipe through it, its pieces as tiles of the
  picture that fly together, a light that sweeps it, a blur that resolves. Never redraw it, never trace it.
- A logo on a busy ground (the op says "kept"): use it on a matching ground or in a frame, or ask for the file.
- No logo: the brand's name set as a wordmark in a strong face from the brand's look; say so, and never draw a symbol
  the brand does not have.

## 3. The story (stop: the user chooses)

Read the kind's guide (types/launch.md for a logo, a reel or a teaser; types/explainer.md; types/music.md for a reel;
types/data.md for numbers) and story.md. Write three storylines that are three different films, in words only: each
its opening image, its turn, its worlds and its end. Show them as a question with three options, the one you
recommend first. Stop and wait for the choice.

## 4. The look (stop: the user chooses)

Read look.md and motion.md, and list the style presets (page_read "@hyperframes/hyperframes/assets/frame-presets/").
Take the two or three that fit the brand and read their FRAME.md. Make each the brand's own: its colours (the logo op's
palette first), its fonts, its mark, and a frame language held through the film (corner marks, a counter "03 / 11", a
timecode, a running label, a grid): the details that make a piece feel designed. Write a spec (spec.md) for the chosen
storyline: every adjective a number, the shots by frame, the defaults you will not use. Keep it as "<brand>-reel/spec.md"
(page_write), so the page writer reads it with every brief.

Have one small project built per look ("<brand>-look-a" ...: page_build, its preset's FRAME.md in "query") holding the
two most telling moments of the storyline, and render them as stills (render_html "frames"). Show them, and ask which look, as a question with options. Stop and wait.

## 5. The music (stop: the user approves)

Plan one "generate" step on the studio's music workflow (MiniMax Music 3): an instrumental (no lyrics unless the user
asked for a song), described in three parts as its guide says: style with a tempo in BPM and a key, then "no vocals",
then the arrangement (an intro, a build, the drop where the turn lands, the end). Its length: the next of 30, 60 or
120 s longer than the film. A logo reveal may take no music: sound effects alone (a riser into a hit, a sparkle).
When it is made, run the film tool's beats op on it and keep the beats in the run state (/motion/beats): the cuts,
the hits and the landing of the mark go on beats.

## 6. The film

Have the project written (page_build, a brief for index.html and the first scenes, then one for the rest; the chosen
look's FRAME.md and sound.md in "query"): index.html with one host per scene, the music
(an `<audio>` with an id, data-volume about 0.8, a fade out of 1 s at the end), and the sound effects on what moves
(sound.md: a whoosh on a fast move, an impact or a pop when something lands, a riser before the turn, clicks and typing
on UI, a sparkle on the lockup), never on everything. One scene file per scene. Everything the brand says comes from
the brief; numbers only from the brand.

Render it (render_html "project", the media: the logo, the music, the photos), then look at the review sheets and the notes
and read review.md. What to fix: the words exact, nothing cut or covered, the first frame already showing something (it
is the thumbnail), the last line held long enough to read, the mark landing on a beat. Fix everything you found in one
pass (one page_build brief naming each fix by file and time), check the fixed moments with stills ("frames", quick and cheap), and render the whole again once; at most two
whole renders after the first in all. Each render and each round of tool calls costs the user, so never render to see
whether a small change worked: a still shows it.

## 7. The other shape

Make the second shape as a project of its own ("<brand>-reel-vertical"): types/vertical.md: the layout recomposed
(stacked, bigger type, the safe areas of the apps), never the wide frame cropped. Render and review it the same way.

## 8. What the user gets

Show both videos and one line on what each is. Offer, in one question, the changes most worth making (a word, the
pace, the music, a scene). Keep the project names in the run state (/motion/projects) so a change is an edit of the
project, not a new film.

## Tells to avoid

A logo faded in; a title over a dimmed screenshot; three feature cards as the whole explainer; an invented dashboard;
the logo docked in a corner as the end card; a grid of icons that could be anyone's; text that changes faster than it
can be read; music that stops before the picture; one transition used everywhere.
