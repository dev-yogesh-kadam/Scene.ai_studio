"""The studio's tools as the agent's model sees them: for each, its name, what it does, and the JSON schema of its input.
This is the one place a tool is described. Claude's live session offers them as its own tools (claude.converse, through
the in-process MCP server "studio"); agent.native_tools() reads them from here. What each tool does is in
api/workspace.py (the functions in `tools` of the planning endpoint).

A field that carries structured data is a real JSON type here (an object, an array). The tool functions still take
the same data as JSON text, as sessions begun before typed schemas send it.
"""

from . import edits

S, I, B, N = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "number"}


def _field(base, about, **more):
    """A property: its type (a dict like S) with its description, and anything else (enum, items)."""
    return {**base, "description": about, **more}


# The film tool's ops that are not written whole: render_html and ffmpeg are tools of their own.
FILM_OPS = tuple(op for op in edits.FILM if op not in ("html", "ffmpeg"))
BOOK_TYPES = ("character", "location", "prop", "outfit", "voice", "style", "script")
MEMORY_OPS = ("remember", "recall", "forget")

ITEM = _field(I, "A library id: an item of this project (a picture, clip, sound or text).")
REF = _field({"type": ["integer", "string"]}, "A library id, or \"$state:/path\" for the id kept at that path.")
ASSET = _field(I, "A NeuralCore entry's id (its \"asset\").")
OFFSET = _field(I, "Where to start reading, in characters, for the next page of a long result (0 for the start).")

# Every tool, in the order the model is shown them: name -> (what it does, its input schema).
TOOLS = {
    "find_assets": (
        "Finds NeuralCore's entries that match some words. Use it before you say NeuralCore has nothing. With \"op\" \"all\" "
        "it looks in the user's other projects instead: each found entry names its project. Another project is read only; "
        "book_save with that entry's \"asset\" copies it into this project. When several entries of other projects fit what "
        "the user described, show them ([[asset:<id>]], the name, its project, one detail that tells them apart) and ask "
        "which one with \"question\"; with one, use it.",
        {"type": "object", "required": ["query"], "properties": {
            "query": _field(S, "The words to look for."),
            "op": _field(S, "\"all\" to look in the user's other projects instead of this one; \"\" for this project.",
                         enum=["", "all"])}}),
    "look": (
        "Tells you what is in a picture or clip. With \"op\" \"deep\" you get a close study of it: subject, faces and "
        "bodies, clothes and pose, background, composition, shape, light, scene, room, atmosphere, props, motion, the story, "
        "every word written in it and where, and two lists: what to preserve and what to avoid. Study a picture this way "
        "before a prompt that must keep it (an edit, an angle of it, a shot that starts on it, a character or place to "
        "match), and put its preserve list in the prompt and its avoid list among what must not appear.",
        {"type": "object", "required": [], "properties": {
            "item": ITEM, "asset": ASSET,
            "op": _field(S, "\"deep\" for a close study; \"\" for what it shows.", enum=["", "deep"])}}),
    "check_shots": (
        "Checks and prices a plan: you get each step checked and priced, and the ones that cannot run with the reason. Do "
        "this before you answer when a plan is more than one or two steps, and fix what it says.",
        {"type": "object", "required": ["steps"], "properties": {
            "steps": _field({"type": "array", "items": {"type": "object"}},
                            "Your plan's steps, each in the shape of a step of your answer.")}}),
    "review": (
        "Reviews something made: you get the checks of it (who, what, clean, coherence, continuity).",
        {"type": "object", "required": ["item"], "properties": {"item": _field(I, "The library id of what was made.")}}),
    "save_note": (
        "Keeps the direction (see \"Direction\" in the message) for the next messages.",
        {"type": "object", "required": ["text"], "properties": {"text": _field(S, "The whole direction, as it is to be kept.")}}),
    "book_save": (
        "Keeps something in this module's NeuralCore, or names an entry; you get its asset id. A script written here (a "
        "story a skill wrote) is kept with \"op\" \"script\" and \"value\" its text, or \"$state:/script/story\" for the text "
        "kept there, so the user can open it in NeuralCore. NeuralCore belongs to this module alone: other modules of the "
        "project never see its entries, and you never see theirs.\n"
        "How entries hang together: a look of a character (a changed outfit, an injury, a transformation) or a location at "
        "another time of day is an entry of its own named \"<base> - <look>\" (\"Maya - torn sleeve\", \"Kitchen - night\"): "
        "named so, it is linked to its base entry by itself. Never make it always on; name it in the shots that need it, "
        "and the base in all others. /cast shows the links: \"look_of\", \"variant\", \"from_scene\", \"looks\", \"palette\" "
        "and \"relatives\". Before a sheet of a person with a blood relative already in NeuralCore, use up to two of those "
        "relatives' sheets as references (\"a clear family resemblance, a distinct person\"); an in-law gets none.",
        {"type": "object", "required": ["text", "op"], "properties": {
            "text": _field(S, "The entry's name (\"Violet\")."),
            "op": _field(S, "Its type.", enum=list(BOOK_TYPES)),
            "item": _field(I, "A library id to add: a sheet you made, a file the user attached."),
            "asset": _field(I, "The entry to change, or an entry of another project to copy here."),
            "value": _field(S, "What it shows, when you know better than NeuralCore; for a script, its text or "
                               "\"$state:/path\" of the text."),
            "settings": {"description": "\"always\" to attach it to every shot of this module, or an object of the entry's "
                                        "fields (with \"always\": true if wanted).",
                         "anyOf": [{"type": "string"}, {"type": "object", "properties": {
                             "always": _field(B, "Attach it to every shot of this module."),
                             "look_of": _field(I, "The base entry's id (0 to unlink)."),
                             "variant": _field(S, "The look, in a few words (\"torn sleeve\")."),
                             "from_scene": _field(I, "The scene the look starts in."),
                             "palette": _field(S, "A location's two muted colours (\"cold steel-blue shadows, warm sodium "
                                                  "highlights\")."),
                             "relations": _field({"type": "array", "items": {"type": "object", "required": ["to", "relation"], "properties": {
                                 "to": _field(I, "A character's entry id: this character is its <relation>."),
                                 "relation": _field(S, "\"mother\", \"brother-in-law\" ..."),
                                 "blood": _field(B, "A blood relative. In-laws and spouses never are.")}}},
                                 "This character's relatives.")}}]}}}),
    "book_import": (
        "Brings an asset sheet into this module's NeuralCore in one call. A sheet attached to the message (a CSV or TSV: one "
        "row an entry, with its type, its name, a link to its picture and notes) is brought in by itself before you are "
        "asked, and its attached item says what came in (\"sheet\"); call this only for a sheet pasted as text (\"value\") "
        "or one in the library that was not attached (\"item\"). Each row's picture is fetched from its link and kept under "
        "its name and type, its notes as how to use it; a row named \"<base> - <look>\" becomes a look of the entry <base>, "
        "or, when there is none, of its group's \"<base> - Face Reference\", from the first scene its notes name. Never "
        "bring a sheet's rows in one by one with import_url. A sheet's entries are the references of this module's work: "
        "every shot takes the entries its scene needs, by name (each character's look for that scene, the location, the "
        "props in it).",
        {"type": "object", "required": [], "properties": {
            "item": _field(I, "The library id of a sheet in the library."),
            "value": _field(S, "The sheet's text, pasted.")}}),
    "page_build": (
        "A motion project's pages written for you by the studio's page writer (a Sonnet, in a call of its own, which gets "
        "the HyperFrames contract, format.md and motion.md), so the pages never sit in this conversation (every round of "
        "tools would read them again, and the user pays for that). It sees the project's files as they are (spec.md too, "
        "so keep the spec there), and gives back what it wrote, HyperFrames' quick check of it, and its notes. A fix is a "
        "brief too (\"compositions/hook.html: the tagline lands at 2.4 s, not 3.1 s; keep the rest\"). Write every HTML file "
        "of a project this way, at most about five files in one call (a bigger project in several: index.html and the "
        "first scenes, then the rest), and never read the pages back with page_read to check them: render stills and look.",
        {"type": "object", "required": ["path", "text"], "properties": {
            "path": _field(S, "The project's name (\"launch\")."),
            "text": _field(S, "The brief, written as a director's: the files to write or change, the shape and fps, each "
                              "scene's time span and what happens in it beat by beat (the beats' times from /motion/beats), "
                              "the look (colours, fonts, the frame language), the exact words, the assets by name "
                              "(assets/logo.png) and the sounds on what moves."),
            "query": _field(S, "More guides it should follow, comma separated "
                               "(\"@hyperframes/hyperframes/references/types/vertical.md, "
                               "@hyperframes/hyperframes/assets/frame-presets/coral/FRAME.md\"), or \"\".")}}),
    "page_write": (
        "Writes one small text file of a motion project you write yourself (its spec.md, a .css of variables, an .svg you "
        "drew), whole. Each module keeps its own projects. Pictures, clips, sounds and fonts are not written here: they "
        "come in at the render as its media (assets/<name>).",
        {"type": "object", "required": ["path", "value"], "properties": {
            "path": _field(S, "\"<project>/<file>\" (\"launch/spec.md\")."),
            "value": _field(S, "The file's whole text, as it is, with no escaping.")}}),
    "page_read": (
        "Reads a motion project's list of files, a file of one, or HyperFrames' own guides, style presets and examples "
        "(read only). Read what the hyperframes skill names before you write.",
        {"type": "object", "required": ["path"], "properties": {
            "path": _field(S, "A project (\"launch\": its files), a file of one, or \"@hyperframes/...\" "
                              "(\"@hyperframes/hyperframes/references/motion.md\", \"@hyperframes/hyperframes/assets/frame-presets/\" "
                              "for the presets)."),
            "offset": OFFSET}}),
    "state_read": (
        "Reads the memory (see \"The memory\" in your instructions): the value kept at a path, or every leaf under a "
        "folder, a page at a time. A run's state is the one place its steps take their inputs from: read it, never what "
        "you remember of the chat. Read it before you ask the user again.",
        {"type": "object", "required": ["path"], "properties": {
            "path": _field(S, "A path (/motion/chunks/c3) or a folder."), "offset": OFFSET}}),
    "state_write": (
        "Keeps a value at a path of the memory; it replaces what was there. A path ending in /* and a value that is an "
        "object of name: value write every leaf of that folder at once. Right after you look at something made or "
        "attached, keep what you saw: \"/assets/<id>/facts\" with an object of photoreal (true/false), has_person "
        "(true/false), subjects ({\"maya\": true}), scene, description and tags ({\"hero\": true}); it is merged into what "
        "is there.",
        {"type": "object", "required": ["path", "value"], "properties": {
            "path": _field(S, "The path to keep it at, or \"<folder>/*\" for every leaf of a folder."),
            "value": {"description": "The value to keep: any JSON (text, a number, an object, a list)."}}}),
    "state_check": (
        "Tells you which names under one folder have nothing under another.",
        {"type": "object", "required": ["path", "against"], "properties": {
            "path": _field(S, "The folder that should cover them."), "against": _field(S, "The folder whose names to check.")}}),
    "film": (
        "One film operation, done on this machine: it costs nothing, and you get the library ids of what it made. Ids are "
        "library ids. A page you design and your own ffmpeg command are render_html and ffmpeg. The ops and their settings:\n"
        "reference {\"image\"} (longer side 1500 px) · slice {\"audio\", \"f_in\", \"f_out\", \"pad\"?: seconds a shorter slice "
        "is filled to with silence at its end} · track {\"frames\": [per block]} · trim {\"video\", \"frames\", \"stretch\"?, "
        "\"size\"?} · retime {\"video\", \"frames\", \"lines\": [{\"master\": [s, e], \"clip\": [s, e]}]} · proof {\"video\", "
        "\"marks\": [{\"at\", \"label\"}]} · subtitles {\"video\", \"lines\": [{\"start\", \"end\", \"text\", \"speaker\", "
        "\"lead\"}], \"style\"?: {\"font\", \"size\", \"colour\", \"outline\", \"outline_colour\", \"shadow\", \"place\": "
        "bottom|middle|top, \"margin\", \"box\", \"highlight\", \"karaoke\": word|fill}, \"words_from\"?: the transcription "
        "with its words' times, for karaoke} · film {\"clips\": [ids], \"audio\"} · speech {\"audio\", \"lines\": [{\"n\", "
        "\"start\", \"end\", \"speaker\"}], \"narrator\"?: the narrator's speaker label, \"save_to\"?: a folder for the spans} "
        "or {\"audio\", \"windows\": [[a, b]]} · reframe {\"video\", \"shape\", \"x\"?, \"y\"?} · outpaint_prep {\"video\", "
        "\"shape\"} · outpaint_join {\"video\", \"parts\": [ids], \"shape\"}. shape is portrait, landscape, square or 4:5.\n"
        "Finding and cutting, no model: shots {\"video\", \"threshold\"?: 0.3, \"min_shot\"?: 0.5} (the cut times and each "
        "shot's span) · keyframes {\"video\", \"from\"?, \"to\"?, and one of \"count\", \"every\" (seconds), \"times\" [s] or "
        "\"shots\" ([{\"n\", \"start\", \"end\"}], one frame each, \"pick\" first|middle|last), \"labels\"?, \"key\"?} "
        "(pictures; with \"save_to\" each is kept at save_to/<n>/<key>, and a captioned copy with its label in a strip below "
        "the frame at save_to/<n>/<key>_captioned) · board {\"stills\": [{\"video\", \"at\"} or {\"image\"}], \"panels\"?: "
        "4|6|9|12|16, \"numbered\"?} (one numbered grid, kept between 0.4 and 2.5 times as wide as tall so a video model "
        "takes it as a reference: 16:9 stills 2 across and 3 down, 9:16 stills 3 across and 2 down; more stills go on more "
        "boards) · beats {\"audio\", \"from\"?, \"to\"?} (tempo, beats, bars) · beat_cut {\"clips\": [ids], \"audio\", "
        "\"every\"?: beats a clip, \"first\"?: the beat to start on, \"beats\"?} · multicam {\"video\", \"cuts\": [{\"at\", "
        "\"camera\": wide|medium|close or one in \"cameras\", \"push\"?: 0 to 0.5}], \"cameras\"?: {name: {\"zoom\", \"x\", "
        "\"y\"}}} (punch-ins cropped from one clip) · gif {\"video\", \"from\"?, \"to\"?, \"fps\"?, \"width\"?} · composite "
        "{\"video\", \"overlay\": a see-through clip or a PNG, \"at\"?, \"x\"?, \"y\"?, \"scale\"?} · audio_check {\"audio\"} "
        "(its length, loudness and silences). shots, keyframes, board and beats take \"save_to\" too.\n"
        "logo {\"logo\": id}: any logo the user gave (a PNG, a JPEG on a flat ground, an SVG kept as text) made ready for "
        "motion: a transparent PNG cut to the mark (and the SVG cleaned beside it), with \"palette\" (the brand's colours, "
        "most used first), \"wants\" (the ground it needs: dark, light or any), \"ground\" (how its own ground was found: "
        "transparent, the colour taken away, or \"kept\" when it was not flat) and, for an SVG, \"shapes\". Use it before any "
        "page shows the logo.",
        {"type": "object", "required": ["op", "settings"], "properties": {
            "op": _field(S, "The operation.", enum=list(FILM_OPS)),
            "settings": _field({"type": "object"}, "The operation's fields, as listed for its op. \"$state:/path\" stands for "
                                                  "the id kept at that path, and \"$state:/folder/*\" for every leaf of a folder.")}}),
    "render_html": (
        "Draws a page or a motion project to video with HyperFrames, on this machine; you get the library ids of what it "
        "made. Look at what it made (look, \"item\" its id) before you build on it, show it or ask about it, and say what "
        "you saw; never ask the user to check what you have not looked at.\n"
        "A single page (\"html\", \"width\", \"height\", \"duration\"): a page you design, with the whole HTML page in "
        "\"html\" (titles, kinetic type, lower thirds, captions styled for a reel, stat and chart cards, layouts over "
        "pictures or clips, end cards); load the html-scenes skill before your first page.\n"
        "A motion project you wrote with page_build (\"project\"): it is checked first (HyperFrames' whole check: its errors "
        "stop it and come back to fix; its warnings come as \"notes\"), then made, with review sheets of its beats, its seams "
        "and the phone view, its sound levelled.\n"
        "The sound effects are there by name: assets/sfx/whoosh.mp3, whoosh-short, whoosh-cinematic, riser, impact-bass-1, "
        "impact-bass-2, pop, click, click-soft, key-press, typing, chime, ping, sparkle, notification, glitch-1, glitch-2, "
        "glitch-3, error. GSAP and its plugins, Three.js and Lottie are there too (their CDN links load the copies here).",
        {"type": "object", "required": [], "properties": {
            "html": _field(S, "A single page: the whole HTML page, as it is."),
            "width": _field(I, "A single page's width in pixels."),
            "height": _field(I, "A single page's height in pixels."),
            "duration": _field(N, "A single page's length in seconds."),
            "project": _field(S, "A motion project's name, instead of html: the project you wrote with page_build."),
            "fps": _field(I, "Frames a second: 30, or 60 for a promo."),
            "format": _field(S, "mp4, webm (see-through), gif, or for a single page png (a still of its last moment).",
                             enum=["mp4", "webm", "gif", "png"]),
            "frames": _field({"type": "array", "items": N}, "A project only: stills of these moments (seconds) instead of the "
                                                            "video, as style frames for the user to approve."),
            "media": _field({"type": "array", "items": {"type": "object", "required": ["name", "item"], "properties": {
                "name": _field(S, "Its file name in the page (\"bg.mp4\", \"logo.png\"): assets/<name> in a project."),
                "item": REF}}}, "Library files the page uses."),
            "review": _field(B, "A project only: make its review sheets (true unless said).")}}),
    "ffmpeg": (
        "Your own ffmpeg command, run in a folder of its own holding only the files you name (any trim, join, crossfade, "
        "grade, speed ramp, punch-in, overlay, mix, duck, caption or measurement); you get the library ids of what it made. "
        "With no outputs you get what ffmpeg said (a measurement). No paths, URLs, devices or shell words: name every file "
        "by its bare name. Load the ffmpeg-recipes skill before your first command, and again when one fails. Look at what "
        "a command made before you build on it or show it.",
        {"type": "object", "required": ["argv", "inputs", "outputs", "reason"], "properties": {
            "argv": _field({"type": "array", "items": S}, "The words after ffmpeg, one string each."),
            "inputs": _field({"type": "array", "items": {"type": "object", "required": ["name", "item"], "properties": {
                "name": _field(S, "Its bare file name in the folder (\"a.mp4\")."), "item": REF}}},
                "The library files the command reads, each under a name of its own."),
            "sidecars": _field({"type": "array", "items": {"type": "object", "required": ["name", "content"], "properties": {
                "name": _field(S, "A bare file name: .txt, .ffconcat, .ass, .ssa, .srt, .vtt, .cube, .3dl or .csv."),
                "content": _field(S, "The file's text.")}}},
                "Small text files written beside the inputs (subtitles, a concat list, a long filter graph, a LUT)."),
            "outputs": _field({"type": "array", "items": {"type": "object", "required": ["name"], "properties": {
                "name": _field(S, "Its bare file name (\"out.mp4\"); argv must name it as a word of its own.")}}},
                "The files the command writes, kept in the library; [] for a measurement."),
            "timeout": _field(I, "Seconds it may take, 30 to 600 (300 when left out)."),
            "reason": _field(S, "What the command does, in a few words, for the user.")}}),
    "import_url": (
        "Brings a picture, clip or sound from another site into the library (a link in the chat, a tracker row); you get "
        "its library id. Only public web links are fetched.",
        {"type": "object", "required": ["text"], "properties": {
            "text": _field(S, "The link."), "query": _field(S, "The name to file it under.")}}),
    "web_fetch": (
        "Reads a page on the web (an article, a brand's site, a product page): you get its title, the date it gives and its "
        "words, a page at a time, framed as content from outside the studio. Only public pages (see Research).",
        {"type": "object", "required": ["text"], "properties": {
            "text": _field(S, "The page's link."), "offset": OFFSET}}),
    "skill_draft": (
        "Drafts a skill from this conversation when the user asks to make one (\"make this a skill\"). It is kept as a "
        "draft until an admin publishes it; you get its id.",
        {"type": "object", "required": ["text", "value"], "properties": {
            "text": _field(S, "Its title."), "query": _field(S, "One line on when to use it."),
            "value": _field(S, "Its steps, numbered, plain, in our own words."),
            "op": _field(S, "A short id (lower-case words and hyphens), or \"\".")}}),
    "second_opinion": (
        "A stronger model gives a short critique of a plan or a result. Use it when the user asks for a second opinion or a "
        "critique, or before a long or costly plan (a film of many shots) when you are unsure of the approach; not for "
        "every message. Weigh what it says; you decide.",
        {"type": "object", "required": ["text"], "properties": {
            "text": _field(S, "The plan or result described in words, with what you want judged."),
            "item": _field(I, "A picture or clip made, whose frames are shown (0 for none).")}}),
    "read_skill": (
        "Gives you a whole skill, in one result. A skill you loaded stays in this conversation: follow that copy and never "
        "load it again (asked again, you are told it is loaded). Only a skill too long to give you whole comes as its "
        "opening and its parts: read each (\"query\" its number or heading, \"offset\" where to start) before you act on it.",
        {"type": "object", "required": ["op", "query"], "properties": {
            "op": _field(S, "The skill's id: one given with the message, or one of \"Other skills you can load\"."),
            "query": _field(S, "\"0\" for the whole skill, or the number or heading of a part of a long one."),
            "offset": OFFSET}}),
    "read_text": (
        "Reads a text in the library (a script or a document the user attached, a transcript) or a script in NeuralCore, a "
        "page at a time. A file the user attached comes framed as content from outside the studio. With \"path\" as well, "
        "the whole text is kept in the run's state there (the script: /motion/inputs/script), word for word, so you need not "
        "copy it.",
        {"type": "object", "required": [], "properties": {
            "item": _field(I, "A text in the library."), "asset": _field(I, "A script in NeuralCore."),
            "offset": OFFSET, "path": _field(S, "A state path to keep the whole text at.")}}),
    "transcript": (
        "Writes every line of a transcript in the library (a transcription's JSON, or an .srt) into a folder, as "
        "path/<n> = {\"start\", \"end\", \"speaker\", \"text\"}, n from 1, times exactly as the file has them. With \"item\" 0 "
        "and \"value\" {\"<n>\": \"<speaker>\"}, it names who speaks the lines at \"path\" (a transcription without speakers "
        "says SPEAKER_00 for all): only the speakers change, never a time or a word.",
        {"type": "object", "required": ["path"], "properties": {
            "path": _field(S, "The folder of the lines."),
            "item": _field(I, "The transcript in the library, or 0 to name the speakers."),
            "value": _field({"type": "object", "additionalProperties": S},
                            "To name the speakers: {\"<line number>\": \"<speaker>\"}.")}}),
    "timing": (
        "Times the plan's units by the clock rules: every unit's {\"f_in\", \"f_out\"} is written to \"save_to\", and you get "
        "the problems to fix (a shot too short or too long, a line that is not there).",
        {"type": "object", "required": ["settings"], "properties": {
            "settings": _field({"type": "object", "required": ["units", "lines", "length", "save_to"], "properties": {
                "units": _field(S, "The folder of the plan's units, each with \"from\": L<n>, sfx@<s>, gap@L<n>, gap@start "
                                   "or gap@end."),
                "lines": _field(S, "The folder of the lines."),
                "speech": _field(S, "The folder of the speech spans."),
                "length": _field(N, "The master's length in seconds."),
                "save_to": _field(S, "The folder for the result.")}}, "Where the timing reads and writes.")}}),
    "preset_search": (
        "Finds craft presets, each with the \"words\" to paste into a prompt, when it fits and what it clashes with (see "
        "Presets).",
        {"type": "object", "required": ["query"], "properties": {
            "query": _field(S, "Words to look for."), "op": _field(S, "A category, or \"\".")}}),
    "memory": (
        "The user's memory across all their projects (see Memory).",
        {"type": "object", "required": ["op"], "properties": {
            "op": _field(S, "What to do.", enum=list(MEMORY_OPS)),
            "path": _field(S, "The key."),
            "value": _field(S, "What to keep (remember), or the words to look for (recall).")}}),
}


def check(tools=TOOLS):
    """[problem] with the definitions: a tool or a property with no description, a required field that is not a
    property, a schema that is not an object. For the tests."""
    problems = []

    def walk(where, schema):
        if not isinstance(schema, dict):
            return problems.append("{} is not a schema".format(where))
        for name, prop in (schema.get("properties") or {}).items():
            if not str((prop or {}).get("description") or "").strip():
                problems.append("{}.{} has no description".format(where, name))
            walk("{}.{}".format(where, name), prop)
        for name in schema.get("required") or []:
            if name not in (schema.get("properties") or {}):
                problems.append("{} requires {}, which it does not have".format(where, name))
        if isinstance(schema.get("items"), dict):
            walk(where + "[]", schema["items"])
        for i, option in enumerate(schema.get("anyOf") or []):
            walk("{}|{}".format(where, i), option)

    for name, (about, schema) in tools.items():
        if not str(about or "").strip():
            problems.append("{} has no description".format(name))
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            problems.append("{}'s input is not an object".format(name))
        walk(name, schema)
    return problems

