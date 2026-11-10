id: html-scenes
title: HTML scenes — motion graphics you design, drawn by HyperFrames
version: 3
desc: Load before writing a page for the render_html tool: the page rules, fonts, media, and how to make titles, lower thirds, captions, stat cards and end cards look designed.
words: (?!)
guide: true
---
The render_html tool draws a page you write to a video with HyperFrames: headless Chrome plays the page frame by
frame, and every frame is exact. Use it for every word on screen and anything designed: titles, kinetic type, lower
thirds, captions styled for a reel, stat and chart cards, quote cards, layouts over a picture or a clip, transitions
in a brand colour, end cards, and stills with exact text (format png: a thumbnail's words over its picture). A video
model cannot write readable words; this can. It is free and made on this machine.

The call: render_html with "html" (the whole page, as it is), "width", "height", "duration", and "fps", "format" and
"media" when needed. You get back the library id of what it made, and "notes" when HyperFrames' check found something worth
fixing. Look at it (look, op deep, for any words in it) before you build on it or show it.

## The page

Each rule is checked before the render, and a page that breaks one comes back with the reason. Fix it and send it again.

1. One root element: `<div id="root" data-composition-id="main" data-start="0" data-duration="D" data-width="W"
   data-height="H">`, where W, H and D are exactly the settings' width, height and duration. Size html, body and the
   root to W x H px, with `overflow: hidden` and `margin: 0`.
2. Every timed element has `class="clip"`, `data-start` and `data-duration` (seconds from the start of the page). An
   element is shown only between its start and its end. Paint order is CSS `z-index`, never the order of the tags.
3. All motion comes from ONE paused GSAP timeline, registered under the root's id:
   ```
   const tl = gsap.timeline({ paused: true });
   ... tl.to / tl.from / tl.fromTo / tl.set, each with its absolute time as the third argument ...
   tl.set({}, {}, D);   // the timeline lasts the whole page
   window.__timelines = window.__timelines || {};
   window.__timelines["main"] = tl;
   ```
   CSS animations and transitions, timers, requestAnimationFrame loops and anything else off the timeline do not render.
   Use tl.set for an instant change. A number that counts up is a tween of a plain object whose onUpdate writes the text.
4. Deterministic: no Math.random (write a small seeded generator if you need scatter), no Date, no fetch. The same page
   must draw the same frames every time.
5. Scripts: GSAP and all its plugins are installed here, free: gsap.min.js, SplitText.min.js, ScrambleTextPlugin.min.js,
   TextPlugin.min.js, DrawSVGPlugin.min.js, MorphSVGPlugin.min.js, MotionPathPlugin.min.js, CustomEase.min.js,
   Flip.min.js, and the rest of gsap/dist. Load them by that bare name (`<script src="SplitText.min.js"></script>`) or by
   their jsDelivr link (cdn.jsdelivr.net/npm/gsap@3.x/dist/...): both load the copy here. Register a plugin before you
   use it: `gsap.registerPlugin(SplitText)`. Every other script is written inline. No iframe, no import, no request.
6. Media: each picture, clip or sound the page shows or plays is given in "media" as {"name": "bg.mp4", "item": its
   library id}, and the page names it by that bare name. Nothing is loaded from the web.
   - Picture: `<img src="hero.png">`, or a CSS `background-image: url(hero.png)` on a child.
   - Clip: `<video id="bg" src="bg.mp4" muted class="clip" data-start="0" data-duration="5" data-media-start="2">`
     plays the clip from its 2nd second. Put `data-has-audio="true"` instead of `muted` to keep its sound.
   - Sound: `<audio src="vo.wav" class="clip" data-start="0.4" data-duration="6" data-volume="1" data-fade-out="0.5">`.
     `data-volume` is gain (1 is as it is, at most 3.98), `data-fade-in` / `data-fade-out` are seconds.
   A video layer makes the render slower: every frame of it is decoded too. Animate the element around it (scale,
   position, opacity, clip-path), never its playback speed.
7. The root shows only a flat colour: put a gradient, a texture or a picture on a child that fills it.
8. Fonts: these load by name with nothing more (`font-family: "Montserrat"`): Inter, Montserrat, Poppins, Outfit, Nunito,
   Oswald, Roboto, Open Sans, Lato, Archivo Black, League Gothic, Playfair Display, EB Garamond, Space Mono, IBM Plex
   Mono, JetBrains Mono, Source Code Pro, Noto Sans JP. Any other name is silently swapped for its nearest one of
   those ("Bebas Neue" becomes League Gothic, "Arial" Inter). For any other Google Font, or the exact one, load it with
   its link in the head and name the weights you use:
   `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@500;800&display=block">`.
   Hindi and other Devanagari text: "Noto Sans Devanagari", "Hind", "Mukta" or "Tiro Devanagari Hindi", by link, and
   set on the element that holds the Hindi words; never let a Latin font fall back to it.
9. Format: mp4 (the default), webm (see-through: nothing behind the words; leave html, body and the root without a
   background), gif (a short loop; slow to make, keep it under 6 s), png (one still of the last moment).
10. Size and length: width and height 16 to 3840 px, even for a video; duration 0.1 to 90 s; fps 24, 25, 30, 50 or 60.
   One render holds about 2,600 million pixels (frames x width x height): 1080x1920 at 30 fps is about 41 s, and about
   13 s with a video layer. Split anything longer into scenes, render each, and join them with the ffmpeg tool.

Before a scene that is joined with the studio's shots, read one shot's facts (width, height) and render at that size.
The studio's shots run at 24 fps: make the scene 24 fps too, or the join judders.

## Making it look designed

The difference between a page that looks made by a designer and one that looks made by a script is mostly these:

**Shape and safe area.** 9:16 (1080x1920) for Reels, Shorts and TikTok: keep every word between x 90 and 990 and
between y 260 and 1440. The app's buttons, captions and caption bar cover the right edge and the bottom quarter, and the
account line covers the top. 16:9 (1920x1080): keep words 96 px in from every edge. 1:1 and 4:5: 80 px.

**Type.** One display face for headings and one text face at most; a single family in two weights is often best.
Sizes on 9:16: headline 110 to 170 px, a second line 52 to 70, captions 64 to 84 bold. On 16:9: headline 96 to 150,
body 40 to 56. A headline on 9:16 holds about 12 to 18 characters a line: break lines by meaning, never mid-phrase.
Big display type sits tight: line-height 0.9 to 1.05, letter-spacing -0.01 to -0.03em. Small labels in capitals open
up: letter-spacing 0.08 to 0.16em. Never more than three sizes on one screen.

**Colour.** Take the palette from the film: look at a frame first, then use its darkest tone as the ground and one
colour from it as the accent. One ground, one ink, one accent; the accent marks the one word that matters, a bar or a
rule, never everything. Words over footage need a scrim (a gradient child from transparent to black at 0.55 to 0.75
behind them) or a text-shadow; never bare white words on a bright sky. A brand's colours and fonts, when NeuralCore or
the user gives them, are used exactly.

**Motion.** Things enter with an ease-out ("power3.out", "expo.out") in 0.4 to 0.8 s and leave with an ease-in
("power2.in") in 0.25 to 0.4 s, faster than they came. Stagger letters 0.02 to 0.05 s apart, words 0.06 to 0.12, lines
0.1 to 0.15. Let moves overlap: the second line starts before the first has landed. A reveal from behind a mask (the
word rises out of a line it was hidden under) looks more finished than a fade; SplitText makes it: `SplitText.create(el,
{ type: "lines", mask: "lines" })`, then tween the lines from yPercent 110. Once words have landed, they hold still
long enough to be read twice: about 0.3 s a word plus a second. A slow drift during the hold (scale 1 to 1.03 over the
whole hold) keeps it alive. Keep to one family of eases in a piece. Fast movers can take motion blur:
`data-motion-blur="on"` on the root.

**Rhythm.** When the piece has music, put its hits on the beats (the beats op gives their times): a word lands, a card
cuts, a number stops on a beat. When it has a voice, a caption word lights when it is said (transcript times).

**One idea a screen.** The biggest thing on the screen is the thing to remember. If a screen needs a paragraph, it is
two screens.

## Patterns

These have been rendered here and work. Adapt them; keep the rules above.

**Title with a mask reveal.**
```
<div id="t" class="clip" data-start="0" data-duration="4">THE NIGHT SHIFT</div>
gsap.registerPlugin(SplitText);
const split = SplitText.create("#t", { type: "lines,chars", mask: "lines" });
tl.from(split.chars, { yPercent: 110, duration: 0.7, ease: "expo.out", stagger: 0.03 }, 0.2);
tl.to(split.lines, { yPercent: -110, duration: 0.35, ease: "power2.in" }, 3.5);
```

**Lower third, see-through (format webm), to lay over a clip.** An accent bar grows, the name and the role rise out of
their masks, hold, and leave in reverse. Bottom-left, inside the safe area, with a text-shadow for any footage under it.
```
tl.from("#bar", { scaleY: 0, duration: 0.5, ease: "expo.out" }, 0.2)
  .from(name.lines, { yPercent: 110, duration: 0.7, ease: "expo.out" }, 0.3)
  .from(role.lines, { yPercent: 110, duration: 0.6, ease: "expo.out" }, 0.45)
  .to([name.lines, role.lines], { yPercent: -110, duration: 0.35, ease: "power2.in", stagger: 0.05 }, D - 0.7)
  .to("#bar", { scaleY: 0, transformOrigin: "top", duration: 0.3, ease: "power2.in" }, D - 0.45);
```
Lay it on with the composite op, or with the ffmpeg tool (see ffmpeg-recipes: overlay a see-through clip).

**Captions that light word by word.** Take the words and their times from the transcript (a few words a group, a
group on screen at a time). Build one span per word, show the group, and light each word when it is said:
```
words.forEach(([w, start, end], i) => {
  tl.to(spans[i], { color: ACCENT, scale: 1.12, duration: 0.12, ease: "power2.out" }, start);
  tl.to(spans[i], { color: INK, scale: 1, duration: 0.12, ease: "power2.in" }, end);
});
```
Spans are `display: inline-block` so they can scale. Bold face, 64 to 84 px, a dark shadow or a box, at y 1150 to
1350 on 9:16 (above the app's own captions).

**A number that counts.**
```
const n = { v: 0 };
tl.to(n, { v: 1240, duration: 1.4, ease: "power2.out",
           onUpdate: () => (stat.textContent = Math.round(n.v).toLocaleString("en-IN")) }, 0.1);
```

**Words over a clip or a picture.** The clip or picture fills the frame (`object-fit: cover`), a scrim child sits over
it, the words over that. A slow push on the picture (scale 1 to 1.08 over the scene) under still words.

**Bars that grow (a chart).** Each bar is a child with `transform-origin: bottom`, tweened from scaleY 0 with a 0.08 s
stagger and "power3.out"; its value label counts up with it and lands with it.

**A transition between two shots.** A see-through page (webm) where a panel in the brand colour wipes across and off
in 0.5 to 0.7 s ("expo.inOut"); lay it over the cut so the cut happens while the panel covers the frame.

**End card.** The name or logo (a picture given as media), one line of what to do next, held 2 to 3 s; the last 0.4 s
fades to the ground colour.

**A series that matches.** Several scenes in one style are one page with only the words, numbers and media changed.
Keep the first page you made (state_write /plan/page, or a note), and write the next scenes from it, so they match.

## When it comes back

- Refused before the render: the reason names each problem (a root that does not match, a file not given, a link off
  the font sites). Fix all of them and send it again.
- HyperFrames' check found a problem: its words say what and how to fix it. Fix and send again.
- "notes" with the result: worth a look (a font that will fall back, contrast), not a failure.
- Look at the result before you use it: every word spelled as you wrote it, nothing cut at an edge or under the safe
  area, the words readable over what is behind them, the timing right (look at frames at the moments that matter).

## A whole piece, as an example

This 14 s, 16:9 piece was rendered here and is the bar for what a page should look like: a ground that lives (soft
lights drifting, a fine grid), a title whose letters rise out of their line under a drawn rule, a statement whose key
word gets a pill that grows behind it, a figure whose ring draws while the number counts, three cards that rise in
turn, a wipe in the accent that covers the cut, and an end card. Every scene enters fast, holds still enough to read,
and leaves faster than it came; moves overlap; one family of eases. Take its craft, never its words or its colours:
the words, palette, fonts and shape come from the work at hand.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<script src="gsap.min.js"></script>
<script src="SplitText.min.js"></script>
<script src="DrawSVGPlugin.min.js"></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&display=block">
<style>
  :root { --ink: #f5f3ee; --soft: #a9a6b8; --a: #ff5c39; --b: #7b5cff; --c: #22d3a6; --ground: #0c0b12; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1920px; height: 1080px; overflow: hidden; background: var(--ground); }
  #root { position: relative; width: 1920px; height: 1080px; overflow: hidden; font-family: "Inter", sans-serif; color: var(--ink); }
  .fill { position: absolute; inset: 0; }
  /* a living ground: three soft lights that drift, a fine grid, grain */
  .light { position: absolute; width: 900px; height: 900px; border-radius: 50%; filter: blur(140px); opacity: .55; }
  #l1 { background: var(--b); left: -200px; top: -300px; }
  #l2 { background: var(--a); right: -250px; bottom: -350px; opacity: .45; }
  #l3 { background: var(--c); left: 700px; top: 600px; opacity: .25; }
  #grid { background-image: linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px);
          background-size: 96px 96px; mask-image: radial-gradient(circle at 50% 50%, #000 30%, transparent 75%); }
  .scene { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; padding: 0 160px; }
  .kicker { font-family: "Space Grotesk"; font-weight: 500; font-size: 30px; letter-spacing: .18em; text-transform: uppercase; color: var(--c); }
  h1 { font-family: "Space Grotesk"; font-weight: 700; font-size: 168px; line-height: .92; letter-spacing: -.035em; margin-top: 28px; }
  h1 em { font-style: normal; color: var(--a); }
  #rule { margin-top: 44px; width: 640px; height: 24px; overflow: visible; }
  .big { font-family: "Space Grotesk"; font-weight: 700; font-size: 104px; line-height: 1.04; letter-spacing: -.03em; max-width: 1500px; }
  .w { display: inline-block; margin-right: .22em; position: relative; }
  .pill { position: absolute; left: -.12em; right: -.12em; top: .1em; bottom: .02em; background: var(--b); border-radius: .22em; z-index: -1; transform-origin: left center; }
  .hl { position: relative; z-index: 0; isolation: isolate; }   /* its own stacking context: the pill stays behind its word, in front of the ground */
  #s3 { flex-direction: row; align-items: center; gap: 120px; }
  #ring { width: 520px; height: 520px; flex: none; position: relative; }
  #ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  #num { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-family: "Space Grotesk"; font-weight: 700; font-size: 150px; letter-spacing: -.04em; }
  #num small { font-size: 70px; color: var(--c); margin-left: 6px; }
  .label { font-size: 56px; font-weight: 600; line-height: 1.15; max-width: 760px; }
  .label span { color: var(--soft); font-weight: 400; display: block; font-size: 36px; margin-top: 22px; }
  #cards { flex-direction: row; align-items: center; justify-content: center; gap: 48px; }
  .card { width: 460px; height: 560px; border-radius: 36px; padding: 52px; display: flex; flex-direction: column; justify-content: space-between;
          background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14); backdrop-filter: blur(20px); }
  .card i { width: 84px; height: 84px; border-radius: 24px; display: block; }
  .card b { font-family: "Space Grotesk"; font-size: 64px; letter-spacing: -.03em; }
  .card p { font-size: 30px; color: var(--soft); line-height: 1.35; margin-top: 14px; }
  #wipe { background: var(--a); transform-origin: left center; }
  #end { align-items: center; text-align: center; padding: 0; }
  #mark { font-family: "Space Grotesk"; font-weight: 700; font-size: 220px; letter-spacing: -.05em; }
  #mark .dot { color: var(--a); }
  #cta { margin-top: 24px; font-size: 40px; color: var(--soft); }
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="14" data-width="1920" data-height="1080">
  <div id="ground" class="fill clip" data-start="0" data-duration="14">
    <div class="light" id="l1"></div><div class="light" id="l2"></div><div class="light" id="l3"></div>
    <div id="grid" class="fill"></div>
  </div>

  <section id="s1" class="scene clip" data-start="0" data-duration="3.4">
    <div class="kicker" id="k1">Scene.ai · Motion</div>
    <h1 id="t1">Ideas that<br><em>move.</em></h1>
    <svg id="rule" viewBox="0 0 640 24"><path id="rulePath" d="M4 14 C 160 2, 320 24, 636 8" stroke="#ff5c39" stroke-width="8" fill="none" stroke-linecap="round"/></svg>
  </section>

  <section id="s2" class="scene clip" data-start="3.2" data-duration="3.4">
    <p class="big" id="t2"><span class="w">Every</span><span class="w">frame</span><span class="w">is</span><span class="w hl"><span class="pill"></span>designed,</span><br><span class="w">not</span><span class="w">templated.</span></p>
  </section>

  <section id="s3" class="scene clip" data-start="6.4" data-duration="3.4">
    <div id="ring"><svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="88" stroke="rgba(255,255,255,.1)" stroke-width="10" fill="none"/>
      <circle id="arc" cx="100" cy="100" r="88" stroke="#22d3a6" stroke-width="10" fill="none" stroke-linecap="round"/></svg>
      <div id="num"><span id="n">0</span><small>%</small></div></div>
    <div class="label" id="lab">of viewers decide in the first second<span>So the first second is the one we design hardest.</span></div>
  </section>

  <section id="cards" class="scene clip" data-start="9.6" data-duration="2.6">
    <div class="card"><i style="background:var(--a)"></i><div><b>Type</b><p>Real fonts, set with care, every word exact.</p></div></div>
    <div class="card"><i style="background:var(--b)"></i><div><b>Motion</b><p>Eased, staggered, overlapping. Never a plain fade.</p></div></div>
    <div class="card"><i style="background:var(--c)"></i><div><b>Rhythm</b><p>Every hit lands on the beat it belongs to.</p></div></div>
  </section>

  <div id="wipe" class="fill clip" data-start="12" data-duration="0.8"></div>

  <section id="end" class="scene clip" data-start="12.3" data-duration="1.7">
    <div id="mark">scene<span class="dot">.</span>ai</div>
    <div id="cta">Make something that moves.</div>
  </section>
</div>
<script>
gsap.registerPlugin(SplitText, DrawSVGPlugin);
const tl = gsap.timeline({ paused: true, defaults: { ease: "expo.out" } });

// the ground drifts the whole time: slow, so it never competes with the words
tl.to("#l1", { x: 520, y: 260, duration: 14, ease: "sine.inOut" }, 0)
  .to("#l2", { x: -460, y: -200, duration: 14, ease: "sine.inOut" }, 0)
  .to("#l3", { x: -600, y: -380, duration: 14, ease: "sine.inOut" }, 0)
  .fromTo("#grid", { scale: 1.15 }, { scale: 1, duration: 14, ease: "none" }, 0);

// 1 · title: kicker, letters rising out of their line, a hand-drawn rule; out upward
const t1 = SplitText.create("#t1", { type: "lines,chars", mask: "lines" });
tl.from("#k1", { y: 30, opacity: 0, duration: .7 }, .15)
  .from(t1.chars, { yPercent: 115, duration: .9, stagger: .025 }, .25)
  .from("#rulePath", { drawSVG: "0%", duration: .9, ease: "power3.inOut" }, .9)
  .to(t1.lines, { yPercent: -115, duration: .45, ease: "power3.in", stagger: .06 }, 2.85)
  .to(["#k1", "#rule"], { opacity: 0, y: -20, duration: .35, ease: "power2.in" }, 2.9);

// 2 · statement: words land one by one, the key word gets a pill that grows behind it
tl.from("#t2 .w", { yPercent: 60, opacity: 0, rotateX: -70, transformOrigin: "50% 100%", duration: .7, stagger: .09 }, 3.3)
  .from("#t2 .pill", { scaleX: 0, duration: .55, ease: "power4.out" }, 3.85)
  .to("#t2", { scale: 1.03, duration: 2.6, ease: "none" }, 3.6)
  .to("#t2 .w", { y: -40, opacity: 0, duration: .35, ease: "power2.in", stagger: .03 }, 6.15);

// 3 · a figure: the ring draws as the number counts, and they land together
const n = { v: 0 }, num = document.getElementById("n");
tl.from("#ring", { scale: .7, opacity: 0, duration: .8 }, 6.5)
  .fromTo("#arc", { drawSVG: "0%" }, { drawSVG: "0% 82%", duration: 1.5, ease: "power3.out" }, 6.7)
  .to(n, { v: 82, duration: 1.5, ease: "power3.out", onUpdate: () => (num.textContent = Math.round(n.v)) }, 6.7)
  .from("#lab", { x: 80, opacity: 0, duration: .8 }, 6.9)
  .from("#lab span", { x: 60, opacity: 0, duration: .8 }, 7.15)
  .to(["#ring", "#lab"], { x: -120, opacity: 0, duration: .4, ease: "power2.in", stagger: .05 }, 9.45);

// 4 · three cards rise and settle with a little overshoot, one after another
tl.from(".card", { y: 220, rotate: (i) => [-8, 2, 9][i], opacity: 0, duration: .9, ease: "back.out(1.4)", stagger: .12 }, 9.7)
  .from(".card i", { scale: 0, duration: .5, ease: "back.out(2)", stagger: .12 }, 10.1)
  .to(".card", { y: -30, duration: 1.6, ease: "none", stagger: .05 }, 10.6);

// the wipe covers the cut to the end card, then leaves the other way
tl.fromTo("#wipe", { scaleX: 0 }, { scaleX: 1, duration: .35, ease: "power4.in" }, 12)
  .set("#wipe", { transformOrigin: "right center" }, 12.35)
  .to("#wipe", { scaleX: 0, duration: .45, ease: "power4.out" }, 12.35);

// end: the mark scales into place, the line follows, the frame settles
tl.from("#mark", { scale: 1.25, opacity: 0, filter: "blur(18px)", duration: .9 }, 12.35)
  .from("#cta", { y: 24, opacity: 0, duration: .6 }, 12.75)
  .set({}, {}, 14);

window.__timelines = window.__timelines || {};
window.__timelines["main"] = tl;
</script>
</body>
</html>
```
