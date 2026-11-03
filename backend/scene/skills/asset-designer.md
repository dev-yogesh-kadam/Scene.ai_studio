id: asset-designer
title: Reference sheets for a script's whole cast, places and props
version: 1
desc: Use when a script, story or bible needs reference sheets for its recurring characters, creatures, groups, locations and props, so every later picture and video shows them the same way.
craft: true
words: \b(asset list|asset sheets?|reference sheets? for (the|this|my) (script|story|film|cast)|sheets for (the|this|my) (script|story|film|cast)|design (the|my) (cast|assets) for)\b
---
Every subject that recurs gets one fixed look and one sheet, kept in NeuralCore under its name. The look is written
once and repeated word for word by every prompt that shows it; the sheet shows it. Never ask for an input except the
references question below.

1. Subjects and looks (read the script whole first; /source/script when the director kept it):
   - Every character, creature, group, location and prop that recurs, with each scene it appears in (its number and a
     few words). Seen once: no sheet; its shot describes it alone. A person seen only in a photo still gets a sheet. A
     prop always carried by one person rides on their sheet unless it is shot on its own.
   - Read /cast first: an entry NeuralCore has is used as it is (its "visual" word for word) and gets no new sheet.
   - One world for the whole script (era, place, culture), from the script or a stated choice; every face, costume,
     weapon and place belongs to it.
   - A look per subject, kept at /characters/<name>/description or /locations/<name>/description (the director reads
     the same paths). People: ethnicity (from the script's language and names), age, skin tone, build, face, hair,
     wardrobe, what they carry. Anything off normal anatomy gets its exact count and place ("four arms, two from each
     shoulder"); a creature's size against a person ("its shoulder twice a man's height"); a power its one colour,
     texture and light.
   - Relatives: each person's family in the script, blood or in-law (step-relatives and spouses are in-law). Never merge
     two people on a shared surname or a word like "Grandma"; resolve it from who is speaking.
2. The asset list, before anything is made: one block fenced ```csv, header Name,Description, characters then
   locations then props. Name as NeuralCore will keep it; Description its look in a few words, then its scenes ("Sc 2
   stables at dawn; Sc 4 loft at night"), "(given)" for a user's picture, quoted when it has a comma.
3. In the same answer, "question": "Do you have reference images for any of these, or should I make them all?" with
   "I have references" and "Make them all". Nothing is made before the answer; skip it when every asset has a picture.
   With references: they attach them with the names; book_save each under its name and type, read its look from it
   (look "deep"), and make only the rest.
4. The sheets, as image steps on a workflow that takes reference pictures (16:9), each with "keep": {"as": the type,
   "name": the asset's name}. A sheet that needs another as a reference waits for it: each wave is one plan (twelve
   steps at most), and the next wave is planned once its references are made.
   - Order: each family from the oldest down (grandparents, parents, children; the older sibling first); unrelated
     people the most-seen first. Locations, props and each family's first person go in the first wave.
   - A person with a blood relative made before them gets that relative's sheet as a reference, up to two (parents
     before siblings), required; the prompt says per reference: "Image k is <name>, their <relation>: a clear family
     resemblance, a distinct person." In-laws get none. A twin or an impostor is an edit of the first's sheet: "the
     same face, eyes, nose, mouth, skin tone, build and three-panel layout; change only <what the script states>".
   - Layouts: a character in three panels side by side (full body front framed from the chin down, the head out of
     frame; full body back, the same framing; a head-and-shoulders close-up, front, eyes to camera: the only face on
     the sheet). A creature: full body side profile with a plain flat grey human silhouette on the same ground line
     for scale; full body three-quarter front; head close-up. A group: two or three members side by side. A prop: the
     object alone, front and side.
   - Character, creature, group and prop prompt: "<Kind> reference sheet, 16:9, one seamless mid-grey studio
     backdrop: <layout>. <its look, word for word>. Same face, same outfit, same proportions in every view. Hair
     neatly styled. Lighting: a large soft key from front-left at head height, a soft fill from the right one stop
     under, a gentle top light separating the subject from the backdrop; soft shallow shadows. Visible pores and fine
     skin texture, individual hair strands, real fabric weave, seams and wear; natural single-exposure contrast. No
     text, labels, arrows or panel borders, no extra views, no people beyond the views named." Then the style, word
     for word. Not realistic: drop the texture sentences.
   - A location: empty of named characters, lit as the script first shows it; one sheet per time of day it is shown
     in. Each gets a palette from the script's mood there and then: a shadow and a highlight colour, muted and filmic
     ("cold steel-blue shadows, warm sodium highlights, muted and filmic"), never neon, never two saturated hues.
     Prompt: "An establishing frame from live-action film footage, 16:9: <the place, its ways in and out, what stands
     where, the paths characters travel left clear>. Camera at a person's eye height, 24mm, set back so the whole
     layout reads, deep focus; one foreground element partly in frame. Light: <one key source and its direction, the
     rest in shadow>, <haze, dust or rain catching it>. Graded to <the palette>. <Background extras the script puts
     there, or: empty>. Natural exposure, soft highlight roll-off, deep shadows with detail, fine film grain. No text."
     Not realistic: drop "from live-action film footage" and the last sentence but one.
5. Once the base sheets exist, one more wave with them as references:
   - a changed look that recurs after the change (an awakening, new armour, an injury): its own sheet, "the same person
     exactly; only <what changed> changes", kept as "<Name> - <look>" ("Maya - torn sleeve"); then book_save its
     "from_scene" (settings {"from_scene": 4});
   - a look worn only in another time (a flashback, training gear): the same way, so the present outfit never shows
     there;
   - a rider and mount seen together more than once: one sheet of the pair, both sheets as references.
   A location at another time of day is kept as "<Place> - <time>" ("Kitchen - night").
6. Look at every sheet (look "deep") and keep what it shows: book_save "value" with a character's look as the picture
   shows it; for a location its layout at /locations/<name>/layout (what stands where, the ways in and out, the
   light) and book_save settings {"palette": "..."}. Relatives: book_save settings {"relations": [{"to": the
   relative's entry, "relation": "mother", "blood": true}]}. Nothing is made again unless the user asks; list any
   sheet that misses its look or layout.
7. The final list, required: one block fenced ```csv, header Name,Description,NeuralCore, one row per sheet
   (characters, locations, props): the name with its look or time ("Wren - green cloak"); the scenes it is for (a
   changed look only those from its change on); its NeuralCore entry as [[asset:<id>]]. The user's own pictures too.
