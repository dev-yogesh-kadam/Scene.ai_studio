---
name: craft-asset-designer
label: Craft Asset Designer
user_description: Reference sheets for every recurring character, location and prop in a script
description: "Use when a script, story or bible needs reference sheets for its recurring characters, creatures, groups, locations and props, so every later image and video shows them the same way. Writes one fixed look per subject, generates each missing sheet, views it and saves what it shows, then posts one CSV of every asset with its scenes and link. Craft skill: works inside any workflow and for any style. Never triggers on its own: load only when the user or another skill explicitly calls for it."
command: false
---

# Asset Designer

Every subject that recurs gets one fixed look and one sheet. The look is written once and repeated word for word by every prompt that shows it; the sheet shows it.

**Inputs** (never ask for one, except the references question after the asset list):
- `script`: a script, a story or a bible. Required.
- `style`: the content style (2D, 3D, realistic, anime…), or a style preset's name and prompt. Missing: realistic.
- `characters`, `locations`, `props`: images the user already has (a CSV mapping names to images included). Missing: a sheet is made.

## 1. Subjects and looks
- **Subjects:** every character, creature, group, location and prop that recurs, with every scene it appears in (its number and a few words). A subject seen once gets no sheet; its shot prompt describes it alone. A person seen only in a photo still gets a sheet. A prop always carried by one character rides on their sheet unless it is shot on its own.
- **World:** one era, place and culture for the whole script, from the script; else a stated choice. Every face, costume, weapon, prop and place belongs to it.
- **Look:** one fixed description per subject. People: ethnicity (from the script's language and names), age, skin tone, build, face, hair, wardrobe, carried items. Anything that breaks normal anatomy (four arms, four wings, three eyes, a second tail) gets its exact count and placement ("four arms, two from each shoulder"); image and video models fall back to normal anatomy otherwise. A creature's size is stated against a person ("its shoulder twice a man's height"). A power or effect gets one fixed look too: its colour, texture, how its light behaves.
- **Relations:** each person's relatives in the script, each marked blood or in-law (step-relatives count as in-law). Never merge two people on a shared surname or a relational word ("Grandma", "her aunt"); resolve those from who is speaking.
- **Given images:** map the user's images onto the subjects and read their looks from the images, word for word as they show them. Only subjects still without an image get a sheet.

**Asset list.** Mandatory, as soon as the planning is done and before anything is generated: post one block fenced exactly ```csv with every asset the script needs: each sheet §2 and §3 will make, plus each of the user's images.
- Header `Name,Description`, characters, then locations, then props.
- **Name:** the same name the final CSV (§5) will use.
- **Description:** its fixed look in a few words, then the scenes it is for ("Sc 2 stables at dawn; Sc 4 loft at night"); a user image adds "(given)". Quote any Description that contains a comma.

**References.** Right after the list, ask with AskUserQuestion, its only tool call in that response: "Do you have reference images for any of these assets, or should I generate them all from scratch?" with the options "I have references" and "Generate from scratch". Generate nothing until they answer. Skip the question when every asset already has a user image.
- **I have references:** ask them to upload the images with the asset names. Map each one onto its asset and read its look from it (Given images, above), then generate only the rest.
- **Generate from scratch:** go on to §2.

## 2. Sheets
`image_create_edit` with the image model the chat's mode allows (the turn's note "Available image models for this conversation: …"; no note: `seedream-5-0-pro`), `aspect_ratio: 16:9`; the mode sets the resolution. Sheets go out in waves: a sheet goes out once every sheet it references exists, and every ready sheet of a wave goes out in one response. Every sheet prompt ends with the style: the `style` prompt word for word, or the style's name when it has no prompt.

**Family:**
- **Build order:** each family from the oldest generation down (grandparents, then parents, then children; an older sibling before a younger one). Among people who aren't related, the most-seen go first. Locations, props and each family's first person go in the first wave.
- **References:** every character with a blood relative built before them gets that relative's sheet as a reference, up to 2 (parents before siblings). This is required. In-laws get none. The prompt adds, per reference: "Image k is <name>, their <relation>: clear family resemblance, a distinct person."
- **Look-alikes** the plot mixes up (twins, an impostor): the second sheet is an edit of the first: "Image 1 is <name>. Make their twin: the same face, eyes, nose, mouth, skin tone, build and the same three-panel layout. Change only <the differences the script states>."
- **Photo-only person:** built after their closest blood relative, with "Image 1 is <name>, their <relation>: a strong family resemblance, a distinct person, age <N>."

| Sheet | Layout |
|---|---|
| Character | three panels side by side: full body front framed from the chin down, head out of frame · full body back, same framing · head-and-shoulders close-up, front, eyes to camera. The close-up is the only face on the sheet. |
| Creature (one, or one member of a creature kind) | full body side profile, a plain flat grey human silhouette standing beside it on the same ground line for scale · full body three-quarter front · head close-up. |
| Group (soldiers, nobles) | 2–3 members full body, side by side, so every member shares its look. |
| Prop | the object alone, front and side. |

Character, creature, group and prop prompt:
```
<Kind> reference sheet, 16:9, one seamless mid-grey studio backdrop: <layout from the table>.
<its fixed look, word for word from §1>. Same face, same outfit, same proportions in every view. Hair neatly styled, no frizzy flyaway strands.
Lighting: a large soft key from front-left at head height, a soft fill from the right one stop under, a gentle top light separating the subject from the backdrop; soft shallow shadows, no blown highlights.
Visible pores and fine skin texture, no airbrushing; individual hair strands; real fabric weave, seams and wear; hide, scale, metal and stone with real surface detail; natural single-exposure contrast, not HDR.
No plastic waxy skin, no CGI sheen, no text, labels, arrows or panel borders, no extra views, no people beyond the views named.
```
On a style that isn't realistic, drop the texture lines.

**Location:** the place empty of named characters, lit as the script first shows it. A place shown at another time of day gets one sheet per time of day.

**Palette:** each location sheet first gets one palette from the script's mood in that place and its time of day: a shadow colour and a highlight colour, muted and filmic ("cold steel-blue shadows, warm sodium highlights, muted and filmic"). Never neon, never two saturated hues; a power's colour, if the story has one, stays the only saturated hue. It is saved with the sheet and repeated word for word by every later prompt in that place.
```
An establishing frame from live-action film footage, 16:9: <the place, its layout stated: ways in and out, what stands where, the paths characters travel left clear>. Camera at a person's eye height (outdoors, on a natural rise the place offers), 24mm wide lens, set back far enough that the whole layout reads, deep focus; one foreground element partly in frame, midground and background separated by depth and haze.
Light: <its time of day: one key source in the world and its direction, the rest falling into shadow>, <haze, dust, rain or smoke catching it>. Graded to <the palette>.
<extras the script puts there, background only — else: empty>.
Cinema camera optics: natural exposure, highlights rolling off softly, deep shadows that keep detail, slight lens falloff at the edges, fine film grain; real surface wear on stone, metal, glass and ground.
No text, no labels.
```
On a style that isn't realistic, drop "from live-action film footage" and the optics line.

## 3. Changed looks and pairs
A second round, once the base sheets exist, with them as references, all in one response:
- **Changed look:** a look that changes for good and recurs after the change (an awakening, a transformation, new armour) gets its own sheet: same layout and prompt, the base sheet as reference ("the same person exactly; only <what changed> changes"). Save the scene it starts in.
- **Other time:** a look worn only in another time or setting (a flashback, training gear in a montage) gets its sheet the same way; the present outfit never appears in another time or place.
- **Pair:** a rider and mount seen together more than once get one sheet of the pair: the rider in the saddle, both sheets as references.

## 4. View and save
`view_image` every sheet and save what it shows: a character's look; a location's layout (what stands where, its ways in and out, its light, its palette). Staging uses only what a location has. Nothing is regenerated unless the user asks; list any sheet that misses its look or layout.

## 5. CSV
Mandatory: once every sheet is done, post one block fenced exactly ```csv (never another language tag) with every asset, the user's own images included. The skill isn't done until it is posted.
- Header `Name,Description,CDN link`, one row per sheet: characters, then locations, then props.
- **Name:** the display name, plus the look or time of day when it isn't the base sheet ("Wren - green cloak", "Great Hall - night"). No commas in Name.
- **Description:** the scenes it is for, a few words each ("Sc 2 stables at dawn, brushing a horse; Sc 4 loft at night"). A changed look lists only the scenes from its change on. Quote any Description that contains a comma.
- **CDN link:** the asset's `asset_id:<id>` handle alone in the cell; Download .csv and Copy for spreadsheet replace it with the asset's URL. A user image mapped from a CSV keeps the link it came with. Never type a URL.

## State
Every key (`<name>`, `<look>`, `<time_of_day>`) is its display name in lowercase with underscores: "Maya - torn sleeve" → `/characters/maya/looks/torn_sleeve`.
```
/characters/<name>/sheet, look (also creatures, groups)   /characters/<name>/looks/<look>   sheet, from_scene
/characters/<name>/relations/<name>   "<relation>, blood|in-law"
/locations/<name>/sheet, layout, palette (/locations/<name>/sheets/<time_of_day> + its palette when it has several)
/props/<name>/sheet
```
