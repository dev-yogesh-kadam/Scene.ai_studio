id: hyperframes
title: HyperFrames — motion graphics projects, the way HyperFrames' own guides make them
version: 2
desc: Load before any motion graphics project (a logo reveal, a brand reel, an explainer, a launch teaser, kinetic type, a chart): the render contract, the work loop, and where HyperFrames' own guides are.
words: (?!)
guide: true
---
HyperFrames draws an HTML project to video by seeking a paused timeline frame by frame, so every render is identical.
In this studio you direct and the studio's page writer writes: you give page_build a brief for a few files at a time,
it writes them in a call of its own (it always has the contract below, format.md and motion.md), and you draw the
project with the render_html tool ("project"). The pages never come into this conversation, so never read them
back: render stills and look. HyperFrames' own guides (Apache-2.0, adapted here) are read with page_read under
"@hyperframes/": they are the craft behind the best motion graphics this studio makes. Read the ones the direction
needs (the type's guide, story.md, look.md) before you write the brief, and name in page_build's "query" the ones the
writing needs beyond format.md and motion.md (a style preset's FRAME.md, types/vertical.md, sound.md, runtimes.md for
Three.js). Where they name a command of theirs, do what the table below says instead.

## In this studio

| HyperFrames' guides say | Here |
| --- | --- |
| `npx hyperframes init`, a new project | page_build "<name>" with a brief for index.html and the scenes (compositions/<scene>.html), in the shape `@hyperframes/hyperframes/references/format.md` gives; your spec as "<name>/spec.md" with page_write, so the writer sees it |
| `check --json` | done before every render of the project: its errors stop it and come back to you to fix; its warnings come as "notes". To check without the whole render, ask for stills ("frames") |
| `snapshot --at …` | render_html with "frames": [seconds]: stills of those moments (style frames, a look at one moment) |
| `snapshot --review`, REVIEW.md | done after every video render: the review sheets (beats, seams, phone) come back as pictures. Look at them (look, op deep) and write what you find in the run state (/motion/review) |
| `render` | render_html with "project": its name, "fps" (30; 60 for a promo, a reel or a logo), "format" |
| preview, Studio, the desktop app, Framey, publish, `auth`, `usage`, `events`, cloud, lambda | not here: the user sees and approves what you show in the studio |
| `/media-use`: music | the studio's music workflow (MiniMax Music 3), as a "generate" step the user approves; then the film tool's beats op on it |
| `/media-use`: sound effects | there by name in every project: assets/sfx/<name>.mp3 (see the film tool) |
| `/media-use`: images, footage | the user's own files first (attached, NeuralCore); else the studio's picture and video workflows, as steps the user approves. Never stock look-alikes of the brand's real things |
| `/media-use`: logo | the film tool's logo op on whatever logo the user gave: a transparent PNG cut to the mark, its colours, the ground it wants, and for an SVG its cleaned markup to animate shape by shape |
| `media-treatment`, LUTs, grades | the ffmpeg tool (eq, curves, colorbalance, lut3d) on the footage before the project uses it |
| `capture <url>` | web_fetch for the site's words, import_url for its pictures and logo |
| `transcribe` | the studio's transcription workflow |
| `beats` | the film tool's beats op |
| `/hyperframes-registry`, blocks | not here: build the effect yourself, from the guides |
| voiceover, avatar | not here unless the user gives the voice file |

Media in a project are its assets: give each library item in render_html's "media" ({"name": "logo.png", "item": id})
and name it assets/logo.png in the pages. GSAP (with every plugin), Three.js and Lottie load from their usual CDN links
or from lib/gsap/<Name>.min.js; Three.js by `import * as THREE from "three"` (and "three/addons/...").

## The contract (from HyperFrames' guide)

1. Every timed element has `class="clip"`, `data-start` and `data-duration` in seconds, and shows over
   [start, start + duration): land an end state just before its end. `data-track-index` is only a lane; paint order is
   `z-index`.
2. The video's length is the root's `data-duration`: overrun is cut, an early end holds the last frame.
3. Each composition builds one paused timeline and registers it after its tweens:
   `window.__timelines["<data-composition-id>"] = tl`. Host id, scene root id and timeline key are the same.
4. No `Date.now()`, unseeded `Math.random()`, network fetches, timers or `repeat: -1`. Everything visible is a function
   of timeline time.
5. Never tween `display`, `visibility` or `autoAlpha` on a `.clip`; animate a child.
6. No CSS `transform` on an element GSAP transforms; animate transforms, not left/top/width/height. In a scene, `fromTo`,
   never `from`.
7. Never play, pause or seek media. A `<video>` keeps its sound with `data-has-audio="true"`, else it is `muted`; music
   and effects are `<audio>` elements, each with an `id`.
8. Only the bundled fonts resolve by name (Inter, Montserrat, Outfit, Nunito, Oswald, League Gothic, Archivo Black,
   Space Mono, IBM Plex Mono, JetBrains Mono, EB Garamond, Playfair Display, Source Code Pro, Noto Sans JP, Roboto,
   Open Sans, Lato, Poppins); any other family needs its Google Fonts `<link>` or an `@font-face`.
9. Asset paths are `assets/...`, no leading `/`, in scenes too.
10. A scene file puts its styles, markup and scripts inside `<template>` and styles its root as `#root`.
11. Content stays inside the 90% action-safe box, captions and key text inside the 80% title-safe box.
12. Copy, brand colours and swappable media are variables (`data-var-text`, `var(--id)`), so a second shape or a new
    line changes one value.

## The work loop

1. What kind of video it is decides what you read first (below). A film over about 15 s that tells something: its
   type's guide, then `story.md` (three storylines that are three different films; the user picks), then `spec.md`
   (every adjective made a number, the defaults banned by name, the shots by frame).
2. Read `look.md` and `motion.md` before the first scene; `sound.md` before the sound. A style preset
   (`@hyperframes/hyperframes/assets/frame-presets/<name>/FRAME.md`, with its frame-showcase.html as an example) is a
   whole look to start from: list them, read the ones that fit the brand, take one and make it the brand's (its
   colours, its fonts, its mark).
3. Have the project written (page_build): a director's brief, each scene's time span and what happens in it beat by
   beat, the exact words, the colours and fonts, the assets by name, the sounds on what moves. Render stills of the key
   moments first and look at them; then the video.
4. Every render comes back checked. Fix every error, weigh every warning, look at every review sheet; read
   `review.md` and do what it says, all in one pass. Check the fixes with stills, then render the whole once more: at
   most two whole renders after the first. Rendering and every round of tool calls cost the user; a still is cheap.

## What to read

| The request | Read (page_read "@hyperframes/hyperframes/references/...") |
| --- | --- |
| Launch, promo, teaser, feature, logo reveal | types/launch.md |
| Explainer, services, tutorial | types/explainer.md |
| Music-led reel, a cut to a song | types/music.md |
| A chart, numbers | types/data.md |
| Vertical, social | types/vertical.md |
| 3D, generative, a pixel field, ribbons | types/3d.md |
| A character, a mascot | types/character.md |
| A website, kinetic type, a real place | film.md |
| Captions; cards over a talking head | captions.md; overlays.md |
| Eases, titles, cuts, punch-ins, speed, holds, transitions | motion.md |
| Colour, type, composition, frames, texture | look.md |
| Music, sound on actions, the mix | sound.md (and @hyperframes/media-use/audio/references/sfx.md) |
| Scenes, attributes, media, fonts, lint | format.md; runtimes.md for GSAP, Lottie, Three.js and canvas |
| The story, the storyboard, the spec, the review | story.md, storyboard.md, spec.md, review.md |
