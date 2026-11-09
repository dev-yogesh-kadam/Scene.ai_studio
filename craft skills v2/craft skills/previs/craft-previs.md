---
name: craft-previs
label: Craft Previs
user_description: Turn a script into a 3D blockout scene in Blender
description: "Use when a script or story must become a 3D scene in Blender before anything is generated: builds each place at real size, a colour-coded stand-in for every character and all their movement, then places a camera for every planned shot and renders grey clips a video model can follow for positions, moves and timing. Craft skill: works inside any workflow. Never triggers on its own: load only when the user or another skill explicitly calls for it."
command: false
---

# Previs

```
1 Build the scene (set, cast, animation) → approve → 2 Cameras (one per planned shot) → grey clips
```
A previs is a grey 3D blockout: real sizes, every person a coloured stand-in, everyone moving on the scene's clock. It is never shown in the film; it fixes who stands where, who moves when, and what each camera sees.

It runs in the `sandbox` tool. Without that tool, tell the user the Agent Sandbox is off for this workspace and stop. `previs.py` (below) already follows the image's Blender guide and renders with Workbench in seconds: skip reading the guide and the test frame.

**Inputs** (never ask for one):
- `script`: the story, or the scenes to build. Required.
- `plan`: the director's scenes and shots (`in_frame`, `size`, `angle`, `move`, `length_s`). Step 2 needs it; without one, stop after step 1 and say the cameras come from the plan.
- `clips`: which shots each clip holds. Missing: one clip per scene.
- `characters`, `locations`, `props`: sheet paths, with the looks and layouts saved for them.
- `aspect_ratio`: 16:9 when missing.

## 1. Build the scene
One JSON per scene: the place, its set, its cast and every move, on the scene's clock in seconds.

**Clock.** With a plan, the scene lasts as long as its shots added up (`length`), and each action happens inside the shot that shows it; a shot starts where the shots before it end. Without one, a line takes its words at 2.5 words a second and an action its natural time.

**Place.** Metres. The floor's centre is 0, 0; +x is right, +y is the back; the front (−y) is where the master camera stands, so face the place the way most of its shots look. Lay out the location sheet's saved layout ("door on the right wall" → x near +width/2). Inside: `room` [width, depth, height]; outside: `ground` [size]. Real sizes: a door 0.9 × 2.1, a table top 0.75 high, a chair, bench or booth seat 0.45, a counter 0.95, a bed top 0.55, a step 0.18 high and 0.28 deep. Each piece in `set`:
- `name`, `at` [x, y], then `box` [w, d, h] or `cyl` [radius, h]; `turn` in degrees, `z` when it is raised (a window, a shelf, a cup on a table);
- `steps` [w, depth, height] in place of `box` for a stair rising to the back (turn it to rise elsewhere); people stand on it;
- `walk: true` for a stage or platform someone stands on;
- `shade` 0 to 1: 0.3 doors, 0.95 windows, 0.7 by default.

Build only what the scene uses: where people stand, sit, lean or walk round, and what they hold, pass or look at (a folder on the table is a thin box on it).

**Cast.** Everyone in the place for the whole scene, framed or not, extras too (a waitress, a guard). Each: `name` (the sheet's name), `height` (1.78 a man, 1.65 a woman, a child by age), `color`. A creature adds `shape: "creature"` and `length`, its height and length from its sheet. Colours go by first appearance across the whole piece: red, blue, yellow, green, orange, purple, cyan, pink, brown; extras grey. A person keeps their colour in every scene, so read `/previs/cast/<name>/color` first.

**Keys.** Each person's `keys` in time order. Each key has `t` (seconds) and what changes then:
- `at` [x, y]: they walk there from `t` at a walking pace (`run: true` to run, `dur` for exact seconds), facing the way they go;
- `face`: a person's name, a piece's name or [x, y]; they turn to it and keep facing it as it moves;
- `pose`: stand, sit, kneel or lie; sit and lie use the seat or bed under them, and `pose: "stand"` gets them up;
- `off: true` before they enter or after they leave; `off: false` when they appear at the way in, then an `at` key walks them in.

The first key has `at`. A walk is a straight line; add a key at a corner to go round a piece. Sitting: `at` inside the seat. Standing: 0.3 m clear of every piece and 0.5 m from anyone else; two people talking stand 1 to 1.5 m apart.

```json
{"scene": 1, "room": [6, 5, 2.8], "length": 14,
 "set": [{"name": "table", "box": [1.6, 0.9, 0.75], "at": [0, 0.4]},
         {"name": "chair", "box": [0.45, 0.45, 0.45], "at": [-0.55, -0.2]},
         {"name": "door", "box": [0.9, 0.08, 2.1], "at": [2.96, 0], "turn": 90, "shade": 0.3}],
 "cast": [{"name": "Maya", "height": 1.65, "color": "red", "keys": [
            {"t": 0, "at": [-0.55, -0.2], "pose": "sit", "face": "Ravi"},
            {"t": 9, "pose": "stand"}, {"t": 9.5, "at": [2.4, 0], "face": "door"}]},
          {"name": "Ravi", "height": 1.8, "color": "blue", "keys": [
            {"t": 0, "at": [-1.8, 1.2], "face": "Maya"}]}]}
```

Save `previs.py` (below) word for word at `/previs/script`, once. Save each scene's JSON as one string at `/previs/scenes/<n>/json` and each person's colour at `/previs/cast/<name>/color`.

**Run.** One `sandbox` run: `compute: "gpu"`, `background: true`, `resume: true`, `timeout_minutes: 30`, `group: "previs"`; `files`: `{"path": "previs.py", "content": "$state:/previs/script"}` and, for each scene, `{"path": "scene_<n>.json", "content": "$state:/previs/scenes/<n>/json"}` (15 scenes at most a run); `present`: `out/overview_<n>.mp4` with `scene: "scene_<n>.blend"` for each; the command exactly `blender -b --python-exit-code 1 --python previs.py -- build scene_1.json scene_2.json …`. The overview is the whole scene from one raised camera, with names over heads.

When it ends, fix every `WARN` line (someone inside a piece or inside another person) in the JSON and run that scene once more. Link each overview at `/previs/scenes/<n>/overview`, post one CSV `scene,place,cast and colours,overview`, then AskUserQuestion: "Is the blocking right?" with the options Approve, Change something. A change edits only that scene's JSON and reruns only that scene.

## 2. Cameras
Only once the blocking is approved. Add `shots`, and `clips` when given, to each scene's JSON from the plan, one shot per planned shot, in order:

| JSON | From the plan |
|---|---|
| `n`, `len` | the shot's number and `length_s` |
| `frame` | who or what the shot is about: a name, or a list for a two-shot, the speaker first |
| `in_frame` | the people its `in_frame` names |
| `size` | extreme wide, wide, full, medium, medium close, close, extreme close; `insert` for an object |
| `from` | where the camera stands: front, back, left, right, front left, front right, back left, back right, or a person's or piece's name (the camera stands beyond them, looking past them) |
| `angle` | eye (default), low, ultra low, high, overhead, dutch, over the shoulder (with `from`: whose shoulder); a POV is `pov`: whose eyes |
| `lens` | only when the plan names one |

| Plan move | JSON |
|---|---|
| lock, static | `lock: true` |
| none, handheld, snorricam, FPV, rack focus | nothing: the camera stays and keeps its subject framed |
| push in, pull out | `to: {"size": one size tighter or wider}` |
| orbit, arc | `to: {"from": a side 45 to 90° round}` |
| crane up, crane down | `to: {"angle": "high"}` or `{"angle": "low"}` |
| pan, whip pan to someone | `to: {"frame": them}` |
| track, follow, walk with | `track: true` |
| dolly zoom | `to: {"lens": …}`; the size holds |

Every shot gets its own camera; a moving one rides a smooth path with an eased start and stop, and the render cuts to each shot's camera on its first frame. A back-and-forth keeps both cameras on the same side of the two people.

`clips`: `[{"n": <clip>, "shots": [<shot n>, …]}]`. A clip that spans two scenes lists its shots in each, and both scenes go in the same run.

**Run.** As in step 1, with `shoot` in place of `build` and `present`: `out/clip_<c>.mp4` with `scene: "scene_<n>.blend"`, and `out/scene_<n>_shots.png` (each shot's first frame, in order).

Each shot prints `CHECK … sees <names>`, with `MISSING` when someone the plan frames is out of shot (change `from` or `size`) or `UNPLANNED` when someone the plan doesn't name is in it (in the way: change `from`; or meant to be there: add them to `in_frame`). Fix them all and run once more; list any that remain. Link each clip at `/previs/clips/<c>/video` and each sheet at `/previs/scenes/<n>/sheet`, then post one CSV `clip,scene,shots,length,video`.

## State
```
/previs/script               previs.py, word for word
/previs/cast/<name>/color
/previs/scenes/<n>           json, overview, sheet
/previs/clips/<c>            video, scene, shots
```

## previs.py
```python
"""Grey 3D blockout of each scene from its scene JSON (Blender 5.2, headless).
  build: set, colour-coded stand-ins and their animation; renders out/overview_<n>.mp4 (names over heads, 16:9)
  shoot: the same, plus a new camera per shot (moves ride an eased path, cameras switch at markers);
         renders out/clip_<c>.mp4, out/scene_<n>_shots.png, out/frames/s<n>_<m>.png
Usage: blender -b --python-exit-code 1 --python previs.py -- build|shoot scene_1.json [scene_2.json ...]
Prints WARN (staging) and CHECK (who each shot sees) lines."""
import bpy, bmesh, json, math, os, shutil, subprocess, sys, tempfile
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

FPS, STEP = 24, 2
SIZES = {"extreme wide": 8.0, "wide": 3.5, "full": 2.2, "medium": 1.1, "medium close": 0.7, "close": 0.42, "extreme close": 0.2}
LENS = {"extreme wide": 18, "wide": 24, "full": 35, "medium": 40, "medium close": 50, "close": 65, "extreme close": 85, "insert": 85}
SIDES = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0),
         "front left": (-1, -1), "front right": (1, -1), "back left": (-1, 1), "back right": (1, 1)}
COLORS = {"red": "E53935", "blue": "1E66F5", "yellow": "F4C20D", "green": "2EAA4A", "orange": "FF7A00",
          "purple": "8E44EC", "cyan": "00B8D4", "pink": "FF5FA2", "brown": "8B5A2B", "grey": "9E9E9E"}
HEAD = {"stand": (0, .935), "sit": (0, .455), "kneel": (0, .655), "lie": (.39, .065)}  # head centre: forward, up (x height)
TMP = os.path.join(tempfile.gettempdir(), "previs")


def lin(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in c] + [1]


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def mesh_obj(name, build, color):
    bm = bmesh.new()
    build(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new(name, me))
    ob.color = color
    return ob


def empty(name):
    return link(bpy.data.objects.new(name, None))


def box(bm, c, s):
    bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))


def cyl(bm, x, y, z0, z1, rx, ry):
    m = Matrix.Translation((x, y, (z0 + z1) / 2)) @ Matrix.Diagonal((rx, ry, 1, 1))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=1, radius2=1, depth=z1 - z0, matrix=m)


def ball(bm, c, r):
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=r, matrix=Matrix.Translation(c))


def nose(bm, c, h, up=False):
    rot = Matrix.Rotation(0 if up else -math.pi / 2, 4, "X")
    off = Vector((0, 0, .09 * h)) if up else Vector((0, .09 * h, 0))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=.025 * h, radius2=0, depth=.06 * h,
                          matrix=Matrix.Translation(Vector(c) + off) @ rot)


def person(pose, h):  # local: forward +Y, origin under the hips at the support's top
    def build(bm):
        f, u = HEAD[pose]
        if pose == "stand":
            cyl(bm, 0, 0, 0, .5 * h, .09 * h, .06 * h); cyl(bm, 0, 0, .5 * h, .82 * h, .13 * h, .075 * h)
        elif pose == "sit":
            cyl(bm, 0, 0, 0, .39 * h, .13 * h, .075 * h); box(bm, (0, .125 * h, .035 * h), (.17 * h, .25 * h, .07 * h))
            box(bm, (0, .25 * h, -.125 * h), (.17 * h, .07 * h, .25 * h))
        elif pose == "kneel":
            box(bm, (0, -.125 * h, .03 * h), (.17 * h, .25 * h, .06 * h)); cyl(bm, 0, 0, .06 * h, .27 * h, .09 * h, .06 * h)
            cyl(bm, 0, 0, .27 * h, .59 * h, .13 * h, .075 * h)
        else:  # lie, on the back, head toward +Y
            box(bm, (0, -.25 * h, .04 * h), (.17 * h, .5 * h, .08 * h)); box(bm, (0, .16 * h, .06 * h), (.26 * h, .32 * h, .12 * h))
        if pose != "lie":
            cyl(bm, 0, 0, (u - .1) * h, (u - .04) * h, .035 * h, .035 * h)  # neck
        ball(bm, (0, f * h, u * h), .065 * h)
        nose(bm, (0, f * h, u * h), h, up=pose == "lie")
    return build


def creature(h, length):
    def build(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1,
                                  matrix=Matrix.Translation((0, 0, .6 * h)) @ Matrix.Diagonal((.2 * length, .35 * length, .2 * h, 1)))
        for x in (-.12, .12):
            for y in (-.25, .25):
                cyl(bm, x * length, y * length, 0, .5 * h, .04 * length, .04 * length)
        cyl(bm, 0, .35 * length, .6 * h, .85 * h, .06 * length, .06 * length)
        ball(bm, (0, .4 * length, .85 * h), .15 * h)
        nose(bm, (0, .4 * length, .85 * h), h * 1.6)
    return build


class Piece:
    def __init__(s, d, sub=None):
        s.name, s.turn = d["name"].lower(), math.radians(d.get("turn", 0))
        s.x, s.y = d["at"]
        s.z0, s.shade = d.get("z", 0), d.get("shade", .7)
        s.walk = bool(sub) or d.get("walk", False)
        if sub:
            s.kind, s.dims, s.oy = "box", sub[0], sub[1]
        else:
            s.kind, s.dims, s.oy = ("cyl", d["cyl"], 0) if "cyl" in d else ("box", d["box"], 0)
        s.top = s.z0 + s.dims[-1]

    def covers(s, x, y):
        dx, dy = x - s.x, y - s.y
        c, n = math.cos(-s.turn), math.sin(-s.turn)
        lx, ly = dx * c - dy * n, dx * n + dy * c - s.oy
        if s.kind == "cyl":
            return math.hypot(lx, ly) <= s.dims[0]
        return abs(lx) <= s.dims[0] / 2 and abs(ly) <= s.dims[1] / 2

    def make(s):
        def build(bm):
            if s.kind == "cyl":
                cyl(bm, 0, 0, s.z0, s.top, s.dims[0], s.dims[0])
            else:
                box(bm, (0, s.oy, s.z0 + s.dims[2] / 2), s.dims)
        ob = mesh_obj(s.name, build, (s.shade,) * 3 + (1,))
        ob.location, ob.rotation_euler.z = (s.x, s.y, 0), s.turn


def load_pieces(items):
    out = []
    for d in items:
        if "steps" in d:  # [width, depth, height]: steps rise toward the piece's back (+Y before turn)
            w, dep, ht = d["steps"]
            n = max(1, round(ht / .18))
            out += [Piece(d, ((w, dep / n, ht * (i + 1) / n), -dep / 2 + (i + .5) * dep / n)) for i in range(n)]
        else:
            out.append(Piece(d))
    return out


def yaw_to(dx, dy):
    return math.atan2(-dx, dy)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Fig:
    def __init__(s, d, scene):
        s.name, s.scene = d["name"], scene
        s.h, s.shape = d.get("height", 1.75), d.get("shape", "person")
        s.length = d.get("length", s.h * 1.6)
        s.color = lin(COLORS[d.get("color", "grey")])
        s.keys = sorted(d["keys"], key=lambda k: k["t"])
        if "at" not in s.keys[0]:
            raise ValueError(f"{s.name}: the first key needs 'at'")
        s.p0 = pos = tuple(s.keys[0]["at"])
        s.moves, s.events, free = [], [], 0.0
        for k in s.keys:
            start = max(k["t"], free)
            when = start
            if "at" in k and math.dist(k["at"], pos) > .01:
                dur = k.get("dur") or math.dist(k["at"], pos) / (4.0 if k.get("run") else 1.3)
                s.moves.append((start, start + dur, pos, tuple(k["at"])))
                pos, when, free = tuple(k["at"]), start + dur, start + dur
            if "off" in k:
                s.events.append((start, "off", k["off"]))
            for f in ("face", "pose"):
                if f in k:
                    s.events.append((when, f, k[f]))
        s.events.sort(key=lambda e: e[0])

    def state(s, t):
        st = {"off": False, "face": None, "pose": "stand"}
        for when, f, v in s.events:
            if when <= t + 1e-6:
                st[f] = v
        return st

    def pos(s, t):  # (x, y), travel direction or None
        p = s.p0
        for a, b, p0, p1 in s.moves:
            if t >= b:
                p = p1
            elif t >= a:
                u = (t - a) / (b - a)
                return (p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u), (p1[0] - p0[0], p1[1] - p0[1])
            else:
                break
        return p, None

    def pose(s, t):
        return "stand" if s.shape != "person" or s.pos(t)[1] else s.state(t)["pose"]

    def target_yaw(s, t):
        (x, y), moving = s.pos(t)
        if moving:
            return yaw_to(*moving)
        face = s.state(t)["face"]
        if face is None:
            return math.pi  # toward the front
        other = s.scene.figs.get(face.lower()) if isinstance(face, str) else None
        fx, fy = other.pos(t)[0] if other else s.scene.point(face, t)[:2]
        return yaw_to(fx - x, fy - y) if math.dist((fx, fy), (x, y)) > .05 else math.pi

    def offsets(s, t):  # head centre forward and up from the root, top of the head up from the root
        if s.shape != "person":
            return .4 * s.length, .85 * s.h, s.h
        f, u = (v * s.h for v in HEAD[s.pose(t)])
        return f, u, u + .065 * s.h

    def head(s, t, yaw):
        (x, y), _ = s.pos(t)
        z = s.scene.ground(x, y, s.pose(t))
        f, u, top = s.offsets(t)
        return Vector((x - math.sin(yaw) * f, y + math.cos(yaw) * f, z + u)), z + top


class Scene:
    def __init__(s, d, mode):
        s.d, s.n = d, d["scene"]
        w, h = (int(v) for v in (d.get("aspect", "16:9") if mode == "shoot" else "16:9").split(":"))
        k = 480 / min(w, h)
        s.res = (round(w * k / 2) * 2, round(h * k / 2) * 2)
        s.sensor_v, s.sensor_h, s.hw = 36 * min(1, h / w), 36 * min(1, w / h), h / w
        s.pieces = load_pieces(d.get("set", []))
        s.byname = {p.name: p for p in s.pieces}
        s.figs = {f["name"].lower(): Fig(f, s) for f in d.get("cast", [])}
        s.yaws = {}
        s.length = sum(x["len"] for x in d["shots"]) if mode == "shoot" else \
            d.get("length") or max((k["t"] for f in s.figs.values() for k in f.keys), default=0) + 3

    def ground(s, x, y, pose="stand"):  # standing needs a walkable piece; sitting and lying take any
        return max([p.top for p in s.pieces if p.covers(x, y) and (p.walk or pose in ("sit", "lie"))], default=0)

    def yaw(s, fig, t):
        return s.yaws.get((fig.name, round(t * FPS)), fig.target_yaw(t))

    def point(s, ref, t):
        if isinstance(ref, list):
            return Vector((ref + [1.6])[:3])
        key = ref.lower()
        if key in s.figs:
            f = s.figs[key]
            return f.head(t, s.yaw(f, t))[0]
        if key in s.byname:
            p = s.byname[key]
            return Vector((p.x, p.y, p.top))
        raise ValueError(f"scene {s.n}: unknown name '{ref}'")

    def subject(s, ref, t):  # point, top, size scale, piece size, is a person
        key = ref.lower() if isinstance(ref, str) else None
        if key in s.figs:
            f = s.figs[key]
            c, top = f.head(t, s.yaw(f, t))
            return c, top, f.h / 1.75, None, f.shape == "person"
        c = s.point(ref, t)
        p = s.byname.get(key)
        return c, c.z, None, (max(p.dims) if p else .3), False

    def shoot(s, spec, t):  # -> camera position, aim point, lens, roll
        roll = math.radians(15) if spec.get("angle") == "dutch" else 0
        if "pos" in spec:
            return Vector(spec["pos"]), s.point(spec["look"], t), spec.get("lens", 35), roll
        fr_ = spec["frame"]
        refs = fr_ if isinstance(fr_, list) and not isinstance(fr_[0], (int, float)) else [fr_]
        subs = [s.subject(r, t) for r in refs]
        size = spec.get("size", "medium")
        lens = spec.get("lens") or LENS.get(size, 40)
        scales = [x[2] for x in subs if x[2]]
        scale = max(scales, default=1)
        aim = sum((x[0] for x in subs), Vector()) / len(subs)
        top = max(x[1] for x in subs)
        if not scales or size == "insert":
            V, aim_z = 2.5 * max(x[3] or .3 for x in subs), top
        else:
            V, aim_z = SIZES.get(size, 1.1) * scale, None
        if spec.get("pov"):
            pf = s.figs[spec["pov"].lower()]
            yaw = s.yaw(pf, t)
            eye = pf.head(t, yaw)[0] + Vector((-math.sin(yaw) * .15, math.cos(yaw) * .15, 0))
            return eye, Vector((aim.x, aim.y, aim_z if aim_z is not None else top - .4 * V)), lens, roll
        fr = spec.get("from", "front")
        if isinstance(fr, str) and fr in SIDES:
            u = Vector(SIDES[fr]).normalized()
        else:
            u = s.point(fr, t).xy - aim.xy
            u = u.normalized() if u.length > .01 else Vector((0, -1))
        perp = Vector((-u.y, u.x))
        if perp.dot(Vector((0, -1))) < 0:
            perp = -perp  # keep to the front side of the line of action
        spread = max(abs((x[0].xy - aim.xy).dot(perp)) for x in subs) * 2 + .6 * scale
        V = max(V, spread * s.hw)
        if aim_z is None:
            aim_z = max(top - .4 * V, .55 * top)
        d = V * lens / s.sensor_v
        side = Vector((0, 0))
        angle = spec.get("angle", "eye")
        people = [x for x in subs if x[4]]
        eye = 1.6 if size in ("extreme wide", "wide", "full") else (people[0][1] - .1 * scale if people else top)
        if angle == "over the shoulder" and not (isinstance(fr, str) and fr in SIDES):
            fp = s.point(fr, t)  # a pace behind their head; head and shoulder just inside the frame edge
            d = (fp.xy - aim.xy).length + 1.3 * scale
            lens = spec.get("lens") or min(50, max(24, d * s.sensor_v / V))
            tan_half = s.sensor_h / 2 / lens
            side, eye = perp * scale * min(.3 + .2 * tan_half, 1.1 * tan_half), fp.z + .05 * scale
        if angle == "low":
            cz = max(.25, aim_z - d * math.sin(math.radians(25)))
        elif angle == "ultra low":
            cz = .12
        elif angle == "high":
            cz = aim_z + d * math.sin(math.radians(30))
        elif angle == "overhead":
            cz = aim_z + d
        else:
            cz = eye if scales else aim_z + .4 * V
        horiz = .02 if angle == "overhead" else math.sqrt(max(d * d - (cz - aim_z) ** 2, .0001))
        cam = Vector((*(aim.xy + u * horiz + side), cz))
        return cam, Vector((aim.x, aim.y, aim_z)), lens, roll


def ease(u):
    u = min(max(u, 0), 1)
    return u * u * (3 - 2 * u)


def smooth(points, k=.35):  # forward and back one-pole filter: an operator's lag, never a lead
    out = list(points)
    for i in range(1, len(out)):
        out[i] = out[i - 1].lerp(out[i], k)
    for i in range(len(out) - 2, -1, -1):
        out[i] = out[i + 1].lerp(out[i], k)
    return out


def build(sc, mode):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    d = sc.d
    outdoor = "ground" in d
    world = bpy.data.worlds.new("world")
    world.color = (.55, .6, .65) if outdoor else (.12, .12, .12)
    scene.world = world
    gw, gd = (d["ground"], d["ground"]) if outdoor else d["room"][:2]
    mesh_obj("floor", lambda bm: box(bm, (0, 0, -.025), (gw, gd, .05)), (.45, .45, .45, 1))
    if not outdoor:  # walls face the room; a camera behind one sees through its back
        w, dp, ht = d["room"]
        for a, b in (((-w / 2, dp / 2), (w / 2, dp / 2)), ((w / 2, dp / 2), (w / 2, -dp / 2)),
                     ((w / 2, -dp / 2), (-w / 2, -dp / 2)), ((-w / 2, -dp / 2), (-w / 2, dp / 2))):
            def wall(bm, a=a, b=b):
                bm.faces.new([bm.verts.new(v) for v in ((*a, 0), (*b, 0), (*b, ht), (*a, ht))])
            mesh_obj("wall", wall, (.82, .82, .82, 1))
    for p in sc.pieces:
        p.make()

    last = round(sc.length * FPS)
    for f in sc.figs.values():  # turns: at most a full turn a second
        yaw = f.target_yaw(0)
        for fr in range(0, last + 1):
            yaw += max(-math.pi * 2 / FPS, min(math.pi * 2 / FPS, wrap(f.target_yaw(fr / FPS) - yaw)))
            sc.yaws[(f.name, fr)] = yaw

    roots = {}
    for f in sc.figs.values():
        root = roots[f.name] = empty(f.name)
        poses = {"stand": None} if f.shape != "person" else dict.fromkeys(HEAD)
        for pose in poses:
            ob = mesh_obj(f"{f.name}_{pose}", creature(f.h, f.length) if f.shape != "person" else person(pose, f.h), f.color)
            ob.parent = root
            poses[pose] = ob
        prev = "start"
        for fr in list(range(0, last + 1, STEP)) + [last]:
            t = fr / FPS
            (x, y), _ = f.pos(t)
            root.location = (x, y, sc.ground(x, y, f.pose(t)))
            root.rotation_euler.z = sc.yaws[(f.name, fr)]
            root.keyframe_insert("location", frame=fr + 1)
            root.keyframe_insert("rotation_euler", index=2, frame=fr + 1)
            vis = None if f.state(t)["off"] else f.pose(t)
            if vis != prev:
                for pose, ob in poses.items():
                    ob.hide_render = ob.hide_viewport = pose != vis
                    ob.keyframe_insert("hide_render", frame=fr + 1)
                    ob.keyframe_insert("hide_viewport", frame=fr + 1)
                prev = vis
        for k in f.keys:
            x, y = k.get("at", (None, None))
            inside = [p.name for p in sc.pieces if x is not None and p.covers(x, y) and not p.walk and p.top > .05]
            if inside and k.get("pose", "stand") in ("stand", "kneel") and not k.get("off"):
                print(f"WARN scene {sc.n}: {f.name} stands inside {inside[0]} at {k['t']}s")
    for t in sorted({k["t"] for f in sc.figs.values() for k in f.keys}):
        here = [(f.name, f.pos(t)[0]) for f in sc.figs.values() if not f.state(t)["off"]]
        for i, (a, pa) in enumerate(here):
            for b, pb in here[i + 1:]:
                if math.dist(pa, pb) < .35:
                    print(f"WARN scene {sc.n}: {a} and {b} stand inside each other at {t}s")

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = sc.res
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "PNG"
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    shade = scene.display.shading
    shade.light, shade.color_type = "STUDIO", "OBJECT"
    shade.show_shadows, shade.shadow_intensity = True, .35
    shade.show_cavity, shade.show_backface_culling = True, True
    if "light" in d:
        scene.display.light_direction = Vector(d["light"]).normalized()
    scene.frame_start, scene.frame_end = 1, last
    shots = overview(sc, scene, roots) if mode == "build" else cameras(sc, scene)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(f"scene_{sc.n}.blend"))
    return scene, shots


def overview(sc, scene, roots):  # one fixed, raised camera that sees the whole place; names over heads
    xs, ys = [], []
    for p in sc.pieces:
        r = max(p.dims[:2]) / 2
        xs += [p.x - r, p.x + r]; ys += [p.y - r, p.y + r]
    for f in sc.figs.values():
        for k in f.keys:
            if "at" in k:
                xs.append(k["at"][0]); ys.append(k["at"][1])
    if "room" in sc.d:
        xs += [-sc.d["room"][0] / 2, sc.d["room"][0] / 2]; ys += [-sc.d["room"][1] / 2, sc.d["room"][1] / 2]
    cx, cy, wx, wy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    el = math.radians(35)
    dist = max(wx / 2 / (18 / 24), (wy * math.sin(el) + 2.2) / 2 / (10.125 / 24)) + wy / 2
    cd = bpy.data.cameras.new("overview")
    cd.lens, cd.sensor_width, cd.clip_end = 24, 36, 500
    cam = link(bpy.data.objects.new("overview", cd))
    cam.location = (cx, cy - dist * math.cos(el), .8 + dist * math.sin(el))
    cam.rotation_euler = (Vector((cx, cy, .8)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    for f in sc.figs.values():
        cu = bpy.data.curves.new(f"label_{f.name}", "FONT")
        cu.body, cu.size, cu.align_x = f.name, .5 * max(1, dist / 10), "CENTER"
        lab = link(bpy.data.objects.new(f"label_{f.name}", cu))
        lab.parent, lab.location, lab.color = roots[f.name], (0, 0, f.offsets(0)[2] + .25), (1, 1, 1, 1)
        c = lab.constraints.new("TRACK_TO")
        c.target, c.track_axis, c.up_axis = cam, "TRACK_Z", "UP_Y"
        prev = None
        for fr in range(1, round(sc.length * FPS) + 1, STEP):  # the name shows only while they're in the place
            hide = f.state((fr - 1) / FPS)["off"]
            if hide != prev:
                lab.hide_render = hide
                lab.keyframe_insert("hide_render", frame=fr)
                prev = hide
    return []


def cameras(sc, scene):  # a new camera per shot; a moving one rides an eased path, aimed at a smoothed target
    t0, shots = 0.0, []
    for sh in sc.d["shots"]:
        t1 = t0 + sh["len"]
        f0, f1 = round(t0 * FPS) + 1, round(t1 * FPS)
        a_spec = {k: v for k, v in sh.items() if k != "to"}
        b_spec = {**a_spec, **sh.get("to", {})}
        (ca, aa, la, ra), (cb, ab, lb, rb) = sc.shoot(a_spec, t0), sc.shoot(b_spec, t1)
        n = sh["n"]
        frames = list(range(f0, f1 + 1))
        u_of = lambda fr: ease((fr - f0) / max(1, f1 - f0))
        if sh.get("lock"):  # the aim eases from the start framing to the end framing
            aims = [aa.lerp(ab, u_of(fr)) for fr in frames]
        else:  # the aim keeps the subjects framed as they move
            aims = [sc.shoot(a_spec, (fr - 1) / FPS)[1].lerp(sc.shoot(b_spec, (fr - 1) / FPS)[1], u_of(fr)) for fr in frames]
        aim = empty(f"aim_{n}")
        for fr, p in zip(frames, smooth(aims)):
            aim.location = p
            aim.keyframe_insert("location", frame=fr)
        rig = empty(f"rig_{n}")
        lead = sc.figs.get((sh["frame"] if isinstance(sh["frame"], str) else str(sh["frame"][0])).lower())
        if sh.get("pov"):  # at their eyes, carried with their head
            pf = sc.figs[sh["pov"].lower()]
            fwd, up, _ = pf.offsets(t0)
            rig.parent, rig.location = bpy.data.objects[pf.name], (0, fwd + .15, up)
        elif (cb - ca).length < .02:
            rig.location = ca
        else:  # the path: start to end, arcing round the subject when the side changes
            ra_, rb_ = ca - aa, cb - ab
            az0, az1 = math.atan2(ra_.y, ra_.x), math.atan2(rb_.y, rb_.x)
            pts = []
            for i in range(5):
                u = i / 4
                az, dist, c = az0 + wrap(az1 - az0) * u, ra_.xy.length + (rb_.xy.length - ra_.xy.length) * u, aa.lerp(ab, u)
                pts.append(Vector((c.x + math.cos(az) * dist, c.y + math.sin(az) * dist, c.z + ra_.z + (rb_.z - ra_.z) * u)))
            cu = bpy.data.curves.new(f"path_{n}", "CURVE")
            cu.dimensions = "3D"
            sp = cu.splines.new("BEZIER")
            sp.bezier_points.add(len(pts) - 1)
            for bp, p in zip(sp.bezier_points, pts):
                bp.co, bp.handle_left_type, bp.handle_right_type = p, "AUTO", "AUTO"
            path = link(bpy.data.objects.new(f"path_{n}", cu))
            fp = rig.constraints.new("FOLLOW_PATH")
            fp.target, fp.use_fixed_location = path, True
            for fr, v in ((f0, 0), (f1, 1)):  # Bezier keys: an eased start and stop
                fp.offset_factor = v
                fp.keyframe_insert("offset_factor", frame=fr)
            if sh.get("track") and lead:
                rig = path  # the path itself travels with the subject (below)
        if sh.get("track") and lead and not sh.get("pov"):  # keep the start offset to the subject
            p0, base = Vector(lead.pos(t0)[0]), rig.location.copy()
            for fr in frames:
                rig.location = base + Vector((*(Vector(lead.pos((fr - 1) / FPS)[0]) - p0), 0))
                rig.keyframe_insert("location", frame=fr)
        rig = bpy.data.objects[f"rig_{n}"]
        tt = rig.constraints.new("TRACK_TO")
        tt.target, tt.track_axis, tt.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
        cd = bpy.data.cameras.new(f"shot_{n}")
        cd.sensor_width, cd.sensor_fit, cd.clip_start, cd.clip_end = 36, "AUTO", .1, 500
        cam = link(bpy.data.objects.new(f"shot_{n}", cd))
        cam.parent, cam.rotation_euler.z = rig, ra  # dutch roll about the lens axis
        for fr, v in ((f0, la), (f1, lb)):
            cd.lens = v
            cd.keyframe_insert("lens", frame=fr)
        scene.timeline_markers.new(f"shot_{n}", frame=f0).camera = cam
        shots.append((sh, cam, f0, f1))
        t0 = t1
    scene.camera = shots[0][1]
    for sh, cam, f0, f1 in shots:  # who each shot's camera sees on its first and last frame
        seen = []
        for fr in (f0, f1):
            scene.frame_set(fr)
            t = (fr - 1) / FPS
            for f in sc.figs.values():
                if f.state(t)["off"] or f.name.lower() in seen:
                    continue
                c, _ = f.head(t, sc.yaws[(f.name, fr - 1)])
                vs = [world_to_camera_view(scene, cam, c + Vector((dx, dy, dz)) * f.h)  # round the head and shoulders
                      for dz in (0, -.2) for dx, dy in ((0, 0), (.12, 0), (-.12, 0), (0, .12), (0, -.12))]
                if any(0 <= v.x <= 1 and 0 <= v.y <= 1 and v.z > 0 for v in vs):
                    seen.append(f.name.lower())
        want = sh.get("in_frame") or ([sh["frame"]] if isinstance(sh["frame"], str) else [x for x in sh["frame"] if isinstance(x, str)])
        want = [w.lower() for w in want if w.lower() in sc.figs]
        miss, extra = [w for w in want if w not in seen], [w for w in seen if w not in want]
        print(f"CHECK scene {sc.n} shot {sh['n']}: sees {', '.join(seen) or 'nobody'}"
              + (f" | MISSING {', '.join(miss)}" if miss else "") + (f" | UNPLANNED {', '.join(extra)}" if extra else ""))
    return shots


def to_mp4(pattern, start, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", str(start), "-i", pattern,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out], check=True)


def render(sc, scene, shots, parts):
    tmp = os.path.join(TMP, f"s{sc.n}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs("out/frames", exist_ok=True)
    if not shots:
        scene.render.filepath = os.path.join(tmp, "o_")
        bpy.ops.render.render(animation=True)
        to_mp4(os.path.join(tmp, "o_%04d.png"), 1, f"out/overview_{sc.n}.mp4")
        print(f"DONE out/overview_{sc.n}.mp4")
        return
    clips = sc.d.get("clips") or [{"n": sc.n, "shots": [x["n"] for x in sc.d["shots"]]}]
    byn = {sh["n"]: (f0, f1) for sh, _, f0, f1 in shots}
    for c in clips:
        f0, f1 = byn[c["shots"][0]][0], byn[c["shots"][-1]][1]
        scene.frame_start, scene.frame_end = f0, f1
        scene.render.filepath = os.path.join(tmp, f"c{c['n']}_")
        bpy.ops.render.render(animation=True)
        part = os.path.join(tmp, f"c{c['n']}.mp4")
        to_mp4(os.path.join(tmp, f"c{c['n']}_%04d.png"), f0, part)
        parts.setdefault(c["n"], []).append(part)
    for i, (sh, _, f0, _) in enumerate(shots):
        c = next(c for c in clips if sh["n"] in c["shots"])
        src = os.path.join(tmp, f"c{c['n']}_{f0:04d}.png")
        shutil.copy(src, f"out/frames/s{sc.n}_{sh['n']}.png")
        shutil.copy(src, os.path.join(tmp, f"sheet_{i + 1:03d}.png"))
    cols = min(4, len(shots))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(tmp, "sheet_%03d.png"),
                    "-vf", f"tile={cols}x{math.ceil(len(shots) / cols)}:padding=6:margin=6:color=white",
                    "-frames:v", "1", f"out/scene_{sc.n}_shots.png"], check=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    mode, files = args[0], args[1:]
    parts = {}
    for path in files:
        sc = Scene(json.load(open(path, encoding="utf8")), mode)
        scene, shots = build(sc, mode)
        render(sc, scene, shots, parts)
    for n, ps in parts.items():  # a clip that spans scenes joins its parts in scene order
        lst = os.path.join(TMP, f"clip_{n}.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in ps))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", f"out/clip_{n}.mp4"], check=True)
        print(f"DONE out/clip_{n}.mp4")


main()
```
