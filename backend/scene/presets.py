"""The preset library: craft snippets the agent stacks into a picture or video prompt. Each is one craft dimension (a
shot size, a composition, a move, a lens, a light, a palette, an expression, a hook) with the words to paste and when
it fits. A strong prompt stacks several: a size, a composition tied to named things in the shot, an angle when it
means something, a move for video, and at most one value per camera-setting dimension, kept physically coherent.

PRESETS: (id, category, dimension, title, words to paste, when it fits, what it clashes with).
"""

import json
import re
from pathlib import Path

PRESETS = [
    # ---- framing: shot size
    ("ecu", "framing", "shot-size", "Extreme close-up", "extreme close-up filling the frame with a single detail",
     "an eye, a fingertip, a product's texture; a beat of tension or a reveal", ""),
    ("cu", "framing", "shot-size", "Close-up", "close-up on the face, from the chin to the top of the head",
     "a feeling the face carries; a line that matters", ""),
    ("mcu", "framing", "shot-size", "Medium close-up", "medium close-up from mid-chest up",
     "dialogue and talking to camera; the most natural framing for a speaker", ""),
    ("ms", "framing", "shot-size", "Medium shot", "medium shot from the waist up, hands in frame",
     "a gesture or an object being handled; two people talking", ""),
    ("ws", "framing", "shot-size", "Wide shot", "wide shot, the whole body in frame with room around it",
     "action, a walk, a person in their place", ""),
    ("ews", "framing", "shot-size", "Establishing wide", "extreme wide establishing shot, the people small in a large place",
     "the first shot of a scene; scale and loneliness", "close facial detail"),
    # ---- framing: angle
    ("eye-level", "framing", "angle", "Eye level", "camera at eye level", "neutral, honest, the default for people", ""),
    ("low-angle", "framing", "angle", "Low angle", "low angle looking up at the subject",
     "power, threat, heroism; a product made monumental", "top-down"),
    ("high-angle", "framing", "angle", "High angle", "high angle looking down on the subject",
     "smallness, defeat, being watched", ""),
    ("top-down", "framing", "angle", "Top-down", "overhead top-down view, the camera straight above",
     "a table, a recipe, a map, a flat lay of products", "low angle"),
    ("dutch", "framing", "angle", "Dutch tilt", "camera tilted about fifteen degrees off level",
     "unease, madness, a world off balance; use rarely", ""),
    ("ots", "framing", "angle", "Over the shoulder", "over-the-shoulder shot, the near shoulder soft in the foreground",
     "one side of a conversation; it ties two people in space", ""),
    ("pov", "framing", "angle", "Point of view", "point-of-view shot through the character's eyes, hands visible at the bottom of the frame",
     "putting the viewer inside a character; discovery", ""),
    # ---- framing: composition (always tie them to named things in the shot)
    ("thirds", "framing", "composition", "Rule of thirds", "<subject> on the left vertical third, <horizon or line> on the lower third line",
     "almost any shot; name what sits on which third", "centred symmetry"),
    ("centre", "framing", "composition", "Centred symmetry", "symmetrical composition, <subject> dead centre, the frame balanced left and right",
     "corridors, doorways, a confrontation, a hero product", "rule of thirds"),
    ("leading-lines", "framing", "composition", "Leading lines", "<road, rails, fence or wall> leading the eye to <subject>",
     "pulling attention to a small subject in a busy place", ""),
    ("frame-in-frame", "framing", "composition", "Frame within a frame", "<subject> framed by <a doorway, window or arch> in the foreground",
     "isolation, being watched, depth", ""),
    ("negative-space", "framing", "composition", "Negative space", "<subject> small against a large empty area of <sky, wall or sea>",
     "loneliness, calm, room for a title", ""),
    ("foreground", "framing", "composition", "Foreground layer", "<object> soft in the foreground, <subject> sharp in the middle ground",
     "depth; a wide shot that would otherwise feel flat", "deep focus"),
    # ---- framing: coverage
    ("two-shot", "framing", "coverage", "Two-shot", "two-shot with both people in frame, facing each other in profile",
     "the start of a conversation, before the close singles", ""),
    ("insert", "framing", "coverage", "Insert", "insert shot of <object> being used, hands only",
     "a detail the story needs seen: a key, a phone screen, a pour", ""),
    # ---- camera movements
    ("static", "camera-movements", "physical-moves", "Locked off", "the camera stays completely still on a tripod",
     "dialogue, products, a calm moment; lets the action move", "handheld"),
    ("push-in", "camera-movements", "dolly-track", "Slow push in", "slow dolly push in toward <subject>",
     "a realisation, rising tension, drawing the viewer in", "pull back"),
    ("pull-back", "camera-movements", "dolly-track", "Pull back reveal", "slow dolly pull back revealing <what is around>",
     "a reveal of the place or of what the character faces; an ending", "push in"),
    ("tracking", "camera-movements", "dolly-track", "Tracking alongside", "camera tracks alongside <subject> at their pace, keeping them in the same place in frame",
     "a walk, a run, a chase", ""),
    ("orbit", "camera-movements", "physical-moves", "Orbit", "camera orbits slowly around <subject> through ninety degrees",
     "a hero moment, a product, a decision", ""),
    ("crane-up", "camera-movements", "physical-moves", "Crane up", "camera cranes up and away from <subject> to a high view",
     "an ending, a release, showing the scale of the place", ""),
    ("pan", "camera-movements", "pan-tilt", "Slow pan", "slow pan from <A> to <B>",
     "linking two things in one place; following a look", ""),
    ("tilt-up", "camera-movements", "pan-tilt", "Tilt up", "slow tilt up from <feet or base> to <face or top>",
     "an entrance, a reveal of height or power", ""),
    ("handheld", "camera-movements", "human-camera", "Handheld", "handheld camera with a light natural sway",
     "documentary, urgency, a creator talking to camera", "locked off"),
    ("whip", "camera-movements", "pan-tilt", "Whip pan", "fast whip pan with motion blur to <next subject>",
     "energy, a joke's timing, a cut hidden in motion", ""),
    # ---- camera settings (one per dimension, only what the scene motivates)
    ("lens-24", "camera-settings", "lens-type", "Wide lens 24mm", "24mm wide lens", "places, interiors, action close to the camera", "telephoto"),
    ("lens-35", "camera-settings", "lens-type", "35mm", "35mm lens", "natural, documentary, people in their surroundings", ""),
    ("lens-50", "camera-settings", "lens-type", "50mm", "50mm lens", "the eye's own view; medium shots", ""),
    ("lens-85", "camera-settings", "lens-type", "Portrait 85mm", "85mm portrait lens", "faces, close-ups, a soft background", ""),
    ("lens-200", "camera-settings", "lens-type", "Telephoto 200mm", "200mm telephoto lens, compressed background",
     "watching from afar, heat haze, stacked city lights", "wide lens"),
    ("macro", "camera-settings", "lens-type", "Macro", "macro lens, extreme detail", "food, product texture, insects, drops", ""),
    ("f14", "camera-settings", "aperture", "Shallow f/1.4", "shot at f/1.4, very shallow depth of field, creamy background blur",
     "isolating a face or product", "deep focus f/11"),
    ("f28", "camera-settings", "aperture", "f/2.8", "shot at f/2.8, soft background", "portraits that keep a hint of the place", ""),
    ("f11", "camera-settings", "aperture", "Deep focus f/11", "shot at f/11, deep focus, everything sharp from front to back",
     "landscapes, architecture, a group", "shallow f/1.4"),
    ("freeze", "camera-settings", "shutter-speed", "Freeze motion", "fast shutter freezing the motion, droplets sharp in the air",
     "splashes, sport, a jump", "motion blur"),
    ("blur", "camera-settings", "shutter-speed", "Motion blur", "slow shutter with motion blur on the moving parts",
     "speed, crowds, light trails", "freeze motion"),
    ("tungsten", "camera-settings", "white-balance", "Warm tungsten", "warm tungsten white balance", "homes at night, nostalgia", "cool daylight"),
    ("daylight", "camera-settings", "white-balance", "Cool daylight", "cool daylight white balance, slightly blue", "offices, tech, winter", "warm tungsten"),
    ("film-35", "camera-settings", "film-look", "35mm film", "shot on 35mm film, fine grain, gentle halation on highlights",
     "a cinematic, analog feel", "clean digital"),
    # ---- lighting and mood
    ("golden-hour", "lighting-and-mood", "sunlight", "Golden hour", "low golden-hour sun from the side, long warm shadows, glowing rim on hair",
     "romance, nostalgia, a hopeful ending", "overcast"),
    ("blue-hour", "lighting-and-mood", "sunlight", "Blue hour", "blue hour after sunset, deep blue sky, warm windows lit",
     "quiet city moods, endings", ""),
    ("hard-noon", "lighting-and-mood", "sunlight", "Hard noon sun", "hard midday sun from above, short black shadows, bright highlights",
     "heat, deserts, a harsh truth", "soft window light"),
    ("overcast", "lighting-and-mood", "soft-diffused", "Overcast", "soft overcast daylight, no hard shadows, muted colours",
     "drama, melancholy, honest skin", "golden hour"),
    ("window", "lighting-and-mood", "soft-diffused", "Window light", "soft window light from the left, gentle falloff into shadow on the right",
     "interiors, portraits, calm conversations", "hard noon sun"),
    ("rembrandt", "lighting-and-mood", "soft-diffused", "Rembrandt", "key light high at forty-five degrees, a small triangle of light on the shadow cheek",
     "serious portraits, drama", ""),
    ("rim", "lighting-and-mood", "night-artificial", "Rim light", "strong rim light outlining the subject against a dark background",
     "separating a subject from the dark; mystery", ""),
    ("neon", "lighting-and-mood", "night-artificial", "Neon night", "mixed magenta and cyan neon light, wet street reflections",
     "night cities, thrillers, music", "golden hour"),
    ("candle", "lighting-and-mood", "night-artificial", "Candlelight", "warm flickering candlelight, deep shadows around",
     "intimacy, history, secrets", ""),
    ("chiaroscuro", "lighting-and-mood", "night-artificial", "Chiaroscuro", "single hard source, strong contrast, most of the frame in shadow",
     "noir, danger, a confession", "high key"),
    ("high-key", "lighting-and-mood", "product", "High key", "bright even high-key light, almost no shadows, white background",
     "clean products, beauty, tech", "chiaroscuro"),
    ("product-soft", "lighting-and-mood", "product", "Softbox product", "large softbox from above-left, a soft gradient on the surface, a crisp reflection line",
     "bottles, cosmetics, devices", ""),
    # ---- colour palettes
    ("teal-orange", "color-palettes", "two-family", "Teal and orange", "teal shadows and warm orange skin tones",
     "blockbuster, action, travel", "pastel"),
    ("pastel", "color-palettes", "pastel", "Pastel", "soft pastel palette of mint, peach and lilac", "kids, beauty, playful brands", "teal and orange"),
    ("earth", "color-palettes", "neutral-earth", "Earth tones", "earthy palette of ochre, olive and clay brown",
     "rustic, craft, cooking, history", ""),
    ("mono", "color-palettes", "achromatic", "Black and white", "black and white, rich blacks and clean whites", "memory, timelessness, drama", ""),
    ("cool", "color-palettes", "cool", "Cool steel", "cool palette of steel blue, slate and silver", "tech, cold, distance", "warm"),
    ("warm", "color-palettes", "warm", "Warm amber", "warm palette of amber, honey and deep red", "comfort, home, celebration", "cool"),
    # ---- expressions
    ("smile-real", "expressions", "recipes", "Real smile", "a real smile that reaches the eyes, crow's feet, cheeks lifted",
     "warmth, joy; avoids the stiff AI grin", ""),
    ("held-tears", "expressions", "recipes", "Holding back tears", "eyes glistening, chin trembling slightly, lips pressed together",
     "grief, pride, a goodbye", ""),
    ("fear", "expressions", "recipes", "Fear", "eyes wide, brows raised and drawn together, mouth slightly open, shoulders up",
     "horror, a threat appearing", ""),
    ("resolve", "expressions", "recipes", "Quiet resolve", "steady gaze straight ahead, jaw set, brows low and level",
     "a decision, the hero before the climb", ""),
    ("suspicion", "expressions", "eyes", "Suspicion", "eyes narrowed, one brow slightly raised, head tilted back", "mystery, a lie being heard", ""),
    ("glance-away", "expressions", "gaze", "Glance away", "looking down and away from the other person", "shame, shyness, a hidden thought", ""),
    # ---- art styles
    ("photo", "art-styles", "realistic", "Photograph", "a real photograph, natural skin texture, true-to-life colour", "realism", "illustration"),
    ("cinematic", "art-styles", "realistic", "Cinematic still", "a cinematic film still, anamorphic framing, graded colour", "film looks", ""),
    ("anime", "art-styles", "anime", "Anime", "2D anime style, clean line art, cel shading, expressive eyes", "anime projects", "photograph"),
    ("watercolour", "art-styles", "painterly", "Watercolour", "watercolour painting, soft bleeding edges, paper texture", "stories, children's books", ""),
    ("3d-toon", "art-styles", "illustration", "3D animated", "3D animated film style, soft global light, rounded shapes", "family, mascots", ""),
    ("flat-vector", "art-styles", "illustration", "Flat vector", "flat vector illustration, bold shapes, no gradients", "explainers, app ads", "photograph"),
    # ---- realism tags
    ("skin", "realism-tags", "skin-face", "Real skin", "visible pores, fine skin texture, slight unevenness, no airbrushing",
     "close-ups that should not look AI", ""),
    ("candid", "realism-tags", "candid-environment", "Candid", "candid moment, not posed, lived-in background with ordinary clutter",
     "UGC, documentary, lifestyle", ""),
    ("phone", "realism-tags", "format-looks", "Phone footage", "shot on a phone, slight wide-angle distortion, natural auto exposure",
     "UGC ads, creator videos", "35mm film"),
    # ---- scene recipes
    ("opening-establish", "scene-recipes", "opening", "Open on the place", "open wide on the place before any person, then cut closer as the action starts",
     "the first scene of a film", ""),
    ("tension-slow", "scene-recipes", "tension", "Slow the tension", "hold longer shots, push in slowly, keep the threat partly out of frame",
     "suspense", ""),
    ("action-clear", "scene-recipes", "action", "Readable action", "one action per shot, keep the direction of movement the same across cuts, wide for the geography then closer",
     "fights, chases", ""),
    ("ending-release", "scene-recipes", "ending", "Release at the end", "end on a slow pull back or crane up, the music rising, the character small in the place",
     "the last shot", ""),
    ("two-people", "scene-recipes", "relationship", "Two people talking", "two-shot to set them, then over-the-shoulder singles, keep both on the same side of the line",
     "dialogue scenes", ""),
    # ---- ad hooks and structures
    ("hook-visual", "ad-hooks", "visual", "Visual hook", "first two seconds: something unexpected moving close to the camera",
     "stopping the scroll", ""),
    ("hook-question", "ad-hooks", "spoken", "Question hook", "open on a spoken question the viewer has asked themselves", "problem-solution ads", ""),
    ("hook-text", "ad-hooks", "text-overlay", "Text hook", "bold text on screen in the first second stating the result or the problem",
     "sound-off viewing", ""),
    ("line-proof", "ad-hook-lines", "proof", "Proof line", "a concrete number or result in the first line, from the user's own facts",
     "credibility; never invent the number", ""),
    ("line-intrigue", "ad-hook-lines", "intrigue", "Intrigue line", "a line that opens a gap the viewer wants closed: 'nobody tells you this about...'",
     "curiosity", ""),
    ("ad-problem-solution", "ad-structures", "talking-head", "Problem, solution, proof", "hook, the problem felt, the product as the answer in use, the result, an end card with the offer",
     "most product ads", ""),
    ("ad-ugc", "ad-structures", "social-proof", "UGC testimonial", "a person talks to the phone camera about what changed for them, cut with the product in use",
     "trust, social media", ""),
    ("ad-product-only", "ad-structures", "product-only", "Product hero", "macro details, the product turning, it in use, a clean end card",
     "premium products without people", ""),
    ("ad-skit", "ad-structures", "skit-narrative", "Mini story", "a small story with a twist where the product solves the moment",
     "memorable brand ads", ""),
    # ---- subtitle styles and dialogue delivery
    ("subs-classy", "subtitle-styles", "classy", "Classy", "white sentence-case subtitles, bottom centre, soft shadow", "films, interviews", ""),
    ("subs-karaoke", "subtitle-styles", "karaoke", "Karaoke", "word-by-word highlight in the brand colour as each word is spoken", "social, songs", ""),
    ("subs-kinetic", "subtitle-styles", "kinetic", "Kinetic", "two or three words at a time, large, popping in on the beat", "Reels, Shorts", ""),
    ("say-whisper", "dialogue-delivery", "volume", "Whispered", "said in a low whisper, close to the ear", "secrets, horror", ""),
    ("say-urgent", "dialogue-delivery", "pace", "Urgent", "said fast and breathless, words tumbling", "danger, excitement", ""),
    ("say-warm", "dialogue-delivery", "tone", "Warm", "said warmly with a smile in the voice", "comfort, ads, greetings", ""),
]

SCENE_FOLDER = Path(__file__).parent / "scene_presets"
SCENE_CATEGORY = "scene-types"
SCENE_FILLER = {"and", "or", "a", "the", "scene", "scenes", "preset", "presets", "type", "types", "mix", "with", "of", "scene-types"}


def _scenes(folder=SCENE_FOLDER):
    """The scene presets: one file per kind of scene (chase, grief, reveal...), the genre craft a director reads before
    shooting one. Its title is the first heading, its use the line under it, the rest its craft. {id: preset}"""
    found = {}
    for path in sorted(Path(folder).glob("*.md")):
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            continue
        title = lines[0].lstrip("#").strip()
        use = lines[1].strip() if len(lines) > 1 else ""
        found[path.stem] = {"id": path.stem, "category": SCENE_CATEGORY, "dimension": "scene", "title": title,
                            "when": use, "mixes": re.findall(r"`([a-z-]+)`", use), "craft": "\n".join(lines[2:]).strip()}
    return found


SCENES = _scenes()

# The scene recipes of the craft script writer (craft skills v2): the same kinds of scene, and more, written as craft for
# telling the story rather than for shooting it. Searched as "scene-<kind>" in their own category, each given whole.
RECIPE_FOLDER = Path(__file__).parent / "scene_recipes"
RECIPE_CATEGORY = "scene-recipes"
RECIPE_PREFIX = "scene-"


def _recipes(folder=RECIPE_FOLDER):
    """The scene recipes, one file per kind (awakening, backstory, battle...), as {"scene-<kind>": preset}: its title the
    first heading, its use the line under it, the rest its craft."""
    found = {}
    for path in sorted(Path(folder).glob("*.md")):
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            continue
        key = RECIPE_PREFIX + path.stem
        use = lines[1].strip() if len(lines) > 1 else ""
        found[key] = {"id": key, "category": RECIPE_CATEGORY, "dimension": "recipe", "title": lines[0].lstrip("#").strip(),
                      "when": use, "mixes": [RECIPE_PREFIX + m for m in re.findall(r"`([a-z-]+)`", use)], "craft": "\n".join(lines[2:]).strip()}
    return found


RECIPES = _recipes()
FIELDS = ("id", "category", "dimension", "title", "words", "when", "clashes")
CATEGORIES = sorted({p[1] for p in PRESETS} | ({SCENE_CATEGORY} if SCENES else set()) | ({RECIPE_CATEGORY} if RECIPES else set()))
MOST_FOUND = 8


def search(query="", category=""):
    """The presets that fit: every word of `query` in its title, words, use or dimension, in `category` when given.
    A scene preset is found by its name, title or use, never by the words of its craft, and given without its craft."""
    words = str(query or "").lower().split()
    category = str(category or "").strip().lower()
    found = []
    for preset in PRESETS:
        item = dict(zip(FIELDS, preset))
        if category and item["category"] != category:
            continue
        text = " ".join(str(v) for v in item.values()).lower()
        if all(w in text for w in words):
            found.append({k: v for k, v in item.items() if v})
    for kept, its_category in ((SCENES, SCENE_CATEGORY), (RECIPES, RECIPE_CATEGORY)):
        if category not in ("", its_category):
            continue
        for scene in kept.values():
            text = " ".join((scene["id"], scene["title"], scene["when"], scene["category"])).lower()
            if all(w in text for w in words):
                found.append({k: v for k, v in scene.items() if k != "craft"})
    return found[:MOST_FOUND]


def scene_craft(query):
    """The scene presets the query names ("fight", "chase and suspense"), whole: their craft is too long to give more
    than one at a time, so the first named is given and the rest are listed to search next."""
    words = re.findall(r"[a-z-]+", str(query or "").lower())
    named = [w for w in words if w in SCENES]
    if not named or any(w not in SCENES and w not in SCENE_FILLER for w in words):   # "close-up reveal" is a framing search
        return ""
    first = SCENES[named[0]]
    text = "Scene preset {} ({}). {}\n\n{}".format(first["id"], first["title"], first["when"], first["craft"])
    rest = [n for n in dict.fromkeys(named[1:]) if n != first["id"]]
    if rest:
        text += "\n\nAlso named: {}. Search each by its name to read it.".format(", ".join(rest))
    return text


def recipe_craft(query, category=""):
    """The scene recipes the query names ("scene-chase"; in their own category "chase" is enough), whole: the first
    named is given and the rest are listed to search next, as scene_craft does."""
    words = re.findall(r"[a-z-]+", str(query or "").lower())
    if category == RECIPE_CATEGORY:
        words = [w if w in RECIPES or RECIPE_PREFIX + w not in RECIPES else RECIPE_PREFIX + w for w in words]
    named = [w for w in words if w in RECIPES]
    if not named or any(w not in RECIPES and w not in SCENE_FILLER and w != RECIPE_CATEGORY for w in words):
        return ""
    first = RECIPES[named[0]]
    text = "Scene recipe {} ({}). {}\n\n{}".format(first["id"], first["title"], first["when"], first["craft"])
    rest = [n for n in dict.fromkeys(named[1:]) if n != first["id"]]
    if rest:
        text += "\n\nAlso named: {}. Search each by its name to read it.".format(", ".join(rest))
    return text


def for_tool(query, category=""):
    category = str(category or "").strip().lower()
    if category in ("", RECIPE_CATEGORY):
        whole = recipe_craft(query, category)
        if whole:
            return whole
    if category in ("", SCENE_CATEGORY):
        whole = scene_craft(query)
        if whole:
            return whole
    found = search(query, category)
    if not found and category:   # a word not in that category: the whole library
        found = search(query)
    if not found:
        return "No preset fits. Categories: {}.".format(", ".join(CATEGORIES))
    return "\n".join(json.dumps(p, ensure_ascii=False) for p in found)


RULES = """Presets: before you write a picture or video prompt that should look crafted (a film, an ad, a hero shot),
search them with preset_search, one search per craft area the shot needs (size and composition, the move, the light,
the lens, the expression), then paste their "words" into the prompt, filling any <...> with the named things of the
shot ("the lighthouse on the left vertical third"). Stack them: one shot size, at least one composition, an angle when
it means something, a move for video, and at most one value for each camera setting (lens, aperture, shutter, white
balance, film look), only where the scene calls for it. Never stack two that "clashes" names. Categories: """ + ", ".join(CATEGORIES) + """.
Scene presets (category scene-types: """ + ", ".join(SCENES) + """) hold the craft of a kind of scene: what it is
really about, the engines to pick from, staging, camera and cutting, performance, the turn, what renders cleanly and
the traps. Before you plan a scene of one of these kinds, search its name alone ("fight") and read the whole craft;
most scenes mix two or more ("mixes"), so read each that fits, one search per name. Take only what serves the scene's
idea; they are options, not a checklist.
Scene recipes (category scene-recipes: """ + ", ".join(RECIPES) + """) hold the same kinds of scene, and more, as craft for
writing the story (no camera): the script writer reads each kind's recipe whole by searching its name ("scene-chase")."""
