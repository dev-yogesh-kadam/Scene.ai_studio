---
name: craft-anchor
label: Craft Anchor
user_description: One staging image per place and moment, so every clip keeps who stands where
description: "Use when planned shots are about to become clips or stills and the people in a place must all stay present and where they stand across shots and clips: decides which staging states need an anchor image, writes and generates each one, and saves the camera and everyone's positions. Craft skill: works inside any workflow and for any video model. Never triggers on its own: load only when the user or another skill explicitly calls for it."
command: false
---

# Anchor

An anchor is one 16:9 still of a staging state at its first moment: the place, everyone in it where they stand, and its light. It is never shown on screen. Every clip in that state takes it as its first reference, so nobody vanishes, swaps or drifts.

**Inputs** (never ask for one):
- `plan`: the scenes and their shots, each shot with who is in frame and where (`in_frame`). Required.
- `clips`: which shots each clip holds. Missing (stills): each shot is its own clip, named `<scene>_<shot>`.
- `characters`, `locations`, `props`: sheet paths, with the looks and layouts saved for them.

## 1. Staging states
A state is everyone in the place at that moment, whether or not a shot frames them, where they stand, and the light. Walk the shots in order. A new state starts when:
- someone enters or leaves the place, or moves to a new spot in it (sits down, crosses to the window);
- the location changes (inside and outside of one building are two locations);
- the light changes (day to night, a power cut), or the place returns with other people or other spots;
- a look changes (soaked, torn, a new outfit) and carries on into a later clip.

Motion around a spot (gestures, turning, pacing back and forth, standing up from a chair) is not a new state.

## 2. Which states get an anchor
Anchor a state when either is true:
- 2+ people or creatures are in it;
- its shots run across 2+ clips.

No anchor, even when one of those is true:
- a chase or journey: nobody holds a spot and the place keeps changing;
- a montage or a one-shot flash; a flashback that plays as a full scene follows the rules above;
- an insert or macro of an object or a hand;
- an empty place: the location sheet is the anchor;
- one person alone inside one clip: their sheet and the location sheet carry it.

Inside one clip, only a state where someone new enters gets its own anchor; moves, exits and light or look changes there are carried by the shots. A state that opens a clip always follows the rules above.

A place that returns with the same people, spots and light reuses its anchor; otherwise its new anchor uses the same camera.

## 3. Camera
One camera per place, chosen at its first anchor and kept for every later state of that place: standing in the set at a standing person's eye height (seated height if everyone sits, bed height if everyone lies), a normal lens, placed where it sees everyone in the state, looking the way most of the place's shots look. Layout, light and palette come from the location sheet's saved fields.

## 4. Prompt
Seedream bends limbs and drops people unless the prompt follows Keep → Subject → Style: 80–150 words (up to 200 with 4+ figures that have sheets; extras don't count; one short clause each: where, facing, posture, a hand only when it holds something), positive words only (no "no", "without", "never"), one choice each (no "or", "if"), no digits, counts or measures ("a few steps up", never "the third stair") except the Image numbers.
```
Strictly keep the outfit and facial features of the figures in Image 1 and Image 2 completely unchanged.
The figure in Image 1 <stands / sits / lies> <where in the place: near, mid or far; left, centre or right; against which set piece>, <facing which way against the camera>, <posture>, <her/his right/left hand on one object>. The figure in Image 2 <…>, <where against the figure in Image 1>.   (one sentence each)
Live-action film frame, camera <where it stands in the set>, looking toward <what> at <height>, focus on the figure in Image <n>, background soft; <foreground element> in the foreground, <what's behind them> behind them. Maintain the background details of Image <location>.
<Time of day> scene, lit by <the key source> from <its direction against camera>, lighting the side of each face toward it, the far side in shadow; <the place's palette>, <haze, dust or smoke>. Natural exposure, subtle film grain.
```
- Each person is "the figure in Image N", never a name. A creature is "the creature in Image N", its size stated against a person ("its shoulder level with the top of the figure in Image 1's head"). Extras with no sheet are written in words, background only ("a ring of guests in evening dress").
- People face each other or what they are doing. Touching people state who is where against whom ("the figure in Image 2 sits on the edge of the bed, her knees against the figure in Image 1's legs").
- The Keep sentence names every figure and creature in the state, one or many.
- On a style that isn't realistic, drop "Live-action film frame" (the sentence starts at "Camera") and the texture sentence.
- A place with no location sheet: describe its layout in words from the plan, and leave out the "Maintain the background" sentence.
- A changed look with no look sheet: right after the Keep sentence, one sentence of the change ("The gown of the figure in Image 1 is soaked dark with red wine.").

## 5. Generate
All anchors in one response: `image_create_edit` with `model_name: seedream-5-0-pro`, `resolution: 2K`, `aspect_ratio: 16:9` always, even for a 9:16 or 1:1 video (the anchor covers the whole place), references in the prompt's Image order: people, each in the look worn at that state, then creatures and props, the location sheet last. A later state of a place is a new generation from the same camera, never an edit of the earlier anchor.

Then post one CSV in chat: `anchor,scene and state,clips,link`.

## State
```
/anchors/<k>    image, scene, place, camera, positions, clips, from_shot
```
`positions` in set terms ("two paces behind Cal, at the foot of the stair"); `clips` lists every clip that takes this anchor. A clip takes the anchor of every state it covers, in order, first among its references.
