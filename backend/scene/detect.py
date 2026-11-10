"""What can be found in a clip or a song without a model, on this machine: where the shots of a video cut, and the
tempo and beats of its music. Both read ffmpeg's measures in plain Python (no numpy): a 3-minute song takes a second
or two, which is nothing beside a render.
"""

import array
import asyncio
import math
import sys
from pathlib import Path

from .media import MediaError, changes, ffmpeg_path, probe

# ---------------------------------------------------------------- shots

CUT = 0.3          # a scene score over this is a cut (0 the same picture, 1 a different one)
MIN_SHOT = 0.5     # seconds: a cut closer than this to the last one is the same change (a flash, a fast whip)


async def shots(video, threshold=CUT, min_shot=MIN_SHOT):
    """Where a video's shots cut: {"seconds", "cuts": [s, ...], "shots": [{"n", "start", "end", "score"}]}. A cut is
    a frame whose picture differs from the one before by more than `threshold` (ffmpeg's scene score, measured on a
    small copy). Of two cuts closer than `min_shot`, the sharper is kept; a cut within `min_shot` of either end is
    dropped. A dissolve or a slow fade may not be seen as a cut."""
    found = await probe(video)
    if not found["width"]:
        raise MediaError("{} has no picture to look for cuts in.".format(Path(video).name))
    scores = await changes(video)
    if not scores:
        raise MediaError("{} can't be read.".format(Path(video).name))
    step = scores[1][0] - scores[0][0] if len(scores) > 1 else 1 / 24
    length = found["seconds"] or scores[-1][0] + step
    cuts = []   # [(time, score)]
    for t, score in scores[1:]:
        if score <= threshold or t < min_shot or t > length - min_shot:
            continue
        if cuts and t - cuts[-1][0] < min_shot:
            if score > cuts[-1][1]:
                cuts[-1] = (t, score)
            continue
        cuts.append((t, score))
    edges = [0.0] + [t for t, _ in cuts] + [length]
    spans = [{"n": i + 1, "start": round(a, 3), "end": round(b, 3), "score": round(cuts[i - 1][1], 3) if i else None}
             for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    return {"seconds": round(length, 3), "cuts": [round(t, 3) for t, _ in cuts], "shots": spans}


# ---------------------------------------------------------------- beats

RATE = 11025              # the music is read at this rate, mono
HOP = 128                 # samples between two measures: 86 a second, 11.6 ms apart
BANDS = ("lowpass=f=200", "bandpass=f=1200:width_type=o:w=2", "highpass=f=4000")   # kick, snare and voice, hats
TEMPO_RANGE = (60.0, 200.0)   # beats a minute looked for
TEMPO_PRIOR = 120.0       # of two tempos that fit as well, the one nearer this (most songs are 80 to 160)
MAX_SECONDS = 600         # at most ten minutes of a song are read
READ_LIMIT = 600          # seconds ffmpeg may take to read it (a few, as a rule): a hung one is stopped


async def _bands(path, start=0.0, seconds=None):
    """The loudness of each band every HOP samples: one list per band."""
    graph = "[0:a]aresample={r},aformat=channel_layouts=mono,asplit={n}{outs};{bands};{ins}amerge=inputs={n}[out]".format(
        r=RATE, n=len(BANDS), outs="".join("[s{}]".format(i) for i in range(len(BANDS))),
        bands=";".join("[s{0}]{1}[b{0}]".format(i, band) for i, band in enumerate(BANDS)),
        ins="".join("[b{}]".format(i) for i in range(len(BANDS))))
    span = ["-t", "{:.3f}".format(seconds)] if seconds else []
    process = await asyncio.create_subprocess_exec(
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-ss", "{:.3f}".format(start), *span, "-i", str(path),
        "-filter_complex", graph, "-map", "[out]", "-ar", str(RATE), "-f", "s16le", "-",
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        raw, err = await asyncio.wait_for(process.communicate(), READ_LIMIT)
    except asyncio.CancelledError:
        process.kill()
        raise
    except asyncio.TimeoutError:   # a file ffmpeg hangs on: the job fails instead of waiting for good
        process.kill()
        await process.wait()
        raise MediaError("ffmpeg stopped responding while reading the music and was stopped after {} s.".format(READ_LIMIT))
    if process.returncode != 0:
        raise MediaError("ffmpeg could not read the music: " + err.decode("utf-8", "replace").strip()[-300:])
    return _split(raw)


def _split(raw):
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    n, width = len(BANDS), HOP * len(BANDS)
    hops = len(samples) // width
    out = []
    for b in range(n):
        band = samples[b::n]
        out.append([math.sqrt(math.sumprod(piece, piece) / HOP) / 32768 for piece in
                    (band[k * HOP:(k + 1) * HOP] for k in range(hops))])
    return out


def _mean_around(values, half):
    """Each value's running mean: the mean of the values within `half` measures of it."""
    sums, total = [0.0], 0.0
    for v in values:
        total += v
        sums.append(total)
    n = len(values)
    return [(sums[min(n, k + half + 1)] - sums[max(0, k - half)]) / (min(n, k + half + 1) - max(0, k - half)) for k in range(n)]


def onset_strength(bands):
    """How sharply the sound rises at each measure: the rise of each band's log loudness, summed, less its running
    mean, never below zero."""
    hops = len(bands[0]) if bands else 0
    strength = [0.0] * hops
    for band in bands:
        level = [math.log10(v + 1e-4) for v in band]
        before = -4.0   # silence before the start, so a hit on the first measure counts
        for k in range(hops):
            rise = level[k] - before
            if rise > 0:
                strength[k] += rise
            before = level[k]
    mean = _mean_around(strength, int(RATE / HOP * 0.25))
    return [max(0.0, v - m) for v, m in zip(strength, mean)]


def _tempo(strength, rate):
    """The beat's period in measures (a fraction), found by how well the onsets line up with themselves a period
    later, weighted towards TEMPO_PRIOR. Returns (period, how clear it is: 0 to 1)."""
    shortest, longest = int(rate * 60 / TEMPO_RANGE[1]), int(math.ceil(rate * 60 / TEMPO_RANGE[0]))
    n = len(strength)
    if n < longest * 3:
        raise MediaError("The music is too short to find its tempo (it needs a few seconds).")
    energy = math.sumprod(strength, strength) or 1.0
    fits = {}
    for lag in range(max(shortest - 1, 1), longest + 2):
        fits[lag] = math.sumprod(strength[:n - lag], strength[lag:]) / energy
    def weighted(lag):
        bpm = rate * 60 / lag
        return fits[lag] * math.exp(-0.5 * (math.log2(bpm / TEMPO_PRIOR) / 0.9) ** 2)
    best = max(range(shortest, longest + 1), key=weighted)
    # a fraction of a measure, from the fit of the lags on either side
    a, b, c = fits.get(best - 1, 0), fits[best], fits.get(best + 1, 0)
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0.0
    period = best + max(-0.5, min(0.5, shift))
    return period, max(0.0, min(1.0, b))


def _track(strength, period, tightness=100.0):
    """The beats: the measures that best follow the onsets while keeping close to one period apart (the dynamic
    programming beat tracker of D. Ellis, 2007). Returns measure numbers."""
    n = len(strength)
    peak = max(strength) or 1.0
    local = [v / peak for v in strength]
    score, back = local[:], [-1] * n
    low, high = int(round(period * 0.5)), int(round(period * 2))
    for k in range(n):
        best, where = -1e9, -1
        for p in range(max(0, k - high), k - low + 1):
            value = score[p] - tightness * math.log((k - p) / period) ** 2 / 100
            if value > best:
                best, where = value, p
        if where >= 0 and best > 0:
            score[k] += best
            back[k] = where
    # the last beat: the best score within one period of the end
    tail = range(max(0, n - int(period) - 1), n)
    k = max(tail, key=lambda i: score[i])
    beats = []
    while k >= 0:
        beats.append(k)
        k = back[k]
    beats.reverse()
    # leading measures the tracker could not reach: step back by the period while the music goes on, each on the
    # strongest onset within a quarter period of where it falls
    reach = max(1, int(period / 4))
    while beats and beats[0] - period >= -reach:
        guess = int(round(beats[0] - period))
        near = range(max(0, guess - reach), min(beats[0], guess + reach + 1))
        if not near:
            break
        beats.insert(0, max(near, key=lambda i: strength[i]))
    return beats


def _peaks(strength, rate, gap=0.07):
    """Onsets: measures that are the highest within ±3 and clearly above the music around them."""
    if not strength:
        return []
    floor = 0.15 * max(strength)
    mean = _mean_around(strength, int(rate * 0.5))
    out = []
    for k, v in enumerate(strength):
        if v < floor:
            continue
        window = strength[max(0, k - 3):k + 4]
        if v < max(window) or v - mean[k] < floor * 0.5:
            continue
        if out and (k - out[-1]) / rate < gap:
            continue
        out.append(k)
    return out


async def beats(path, start=0.0, end=None):
    """The tempo and beats of a song (or of a video's sound), from `start` to `end` seconds: {"tempo" (beats a
    minute), "confidence" (0 to 1: how clearly the onsets repeat), "beats": [s, ...], "onsets": [s, ...] (every hit,
    on or off the beat), "bars": [s, ...] (every fourth beat from the strongest of the first four: a guess at the
    downbeats), "seconds"}. Times are in the file's own seconds, about 12 ms exact."""
    found = await probe(path)
    if not found["audio"]:
        raise MediaError("{} has no sound to find beats in.".format(Path(path).name))
    total = found["seconds"]
    end = min(end if end else total, total, start + MAX_SECONDS)
    if end - start < 3:
        raise MediaError("Give at least 3 seconds of music to find its beats.")
    bands = await _bands(path, start, end - start)
    rate = RATE / HOP
    strength = onset_strength(bands)
    period, clear = _tempo(strength, rate)
    marks = _track(strength, period)
    beat_times = [round(start + k / rate, 3) for k in marks if start + k / rate < end]
    # the downbeat guess: of the first four beats, the one whose every fourth beat has the most low end
    low = bands[0]
    def weight(offset):
        return sum(low[k] for k in marks[offset::4] if k < len(low))
    first = max(range(min(4, len(marks))), key=weight) if marks else 0
    return {"tempo": round(60 * rate / period, 1), "confidence": round(clear, 2), "beats": beat_times,
            "onsets": [round(start + k / rate, 3) for k in _peaks(strength, rate)],
            "bars": beat_times[first::4], "seconds": round(end - start, 2)}


def cut_points(beat_times, count, every=1, first=0):
    """The beats a cut falls on, for `count` clips cut every `every` beats starting at beat number `first` (from 0):
    count + 1 times, the last where the last clip ends. Raises MediaError when the music has too few beats."""
    picked = beat_times[first::every][:count + 1]
    if len(picked) < count + 1:
        raise MediaError("The music has {} beats from there, every {}: not enough to cut {} clips on (it needs {}).".format(
            len(beat_times[first::every]), every, count, count + 1))
    return picked
