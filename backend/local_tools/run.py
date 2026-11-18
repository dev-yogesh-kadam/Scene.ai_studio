"""The studio's tools that run on this PC, outside the studio's own Python: transcription (faster-whisper) and voice
separation (Demucs). The studio's "On this PC" provider (scene/providers/local.py) runs this file with the Python of
`.venv-audio` (docs/servers.md, "Tools on this PC"), never importing it: PyTorch and the models stay out of the studio.

    python run.py check                 -> one JSON line: {"transcribe": {"ready", "why"}, "separate_voice": {...}, "device"}
    python run.py <tool> <job folder>   -> JSON lines on stdout: {"progress", "message"} while it works, then
                                           {"done": true, "outputs": [{"name", "mime"}]} or {"error": "words"}

The job folder holds `job.json` ({"input": {...}, "models_dir"}); every output is written next to it.

transcribe: input {"audio" or "video": a file path, "language": "auto" | "en" | "hi" | ..., "speakers": bool}.
  Writes transcript.json, exactly as the ComfyUI workflow it replaces did:
  {"language", "segments": [{"start", "end", "speaker", "text"}], "words": [{"start", "end", "word", "speaker",
  "aligned"}]} (seconds, 3 decimals), and transcript.srt ("[SPEAKER_00] text" a line). Speaker labels need a
  diarization model that is not set up yet: every line is SPEAKER_00 until it is.
separate_voice: input {"audio" or "video": a file path}. Writes voice.wav and music_fx.wav at the input's sample rate
  and exact length, no time shift; music_fx is the input minus the voice, so the two add back up to the input.
"""

import json
import os
import sys
import time
from pathlib import Path

WHISPER_MODEL = os.environ.get("SCENE_WHISPER_MODEL", "large-v3")
DEMUCS_MODEL = "htdemucs"


def say(**fields):
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def device():
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def check():
    found = {"device": device()}
    for tool, modules, install in (("transcribe", ("faster_whisper", "av"), "faster-whisper"),
                                   ("separate_voice", ("torch", "demucs", "soundfile", "av"), "torch demucs soundfile")):
        missing = []
        for module in modules:
            try:
                __import__(module)
            except Exception:
                missing.append(module)
        found[tool] = {"ready": not missing,
                       "why": "" if not missing else "{} not installed: run .venv-audio\\Scripts\\python -m pip install {}".format(
                           ", ".join(missing), install)}
    say(**found)


def source_of(job):
    path = job["input"].get("audio") or job["input"].get("video")
    if not path:
        raise ValueError("Give it an audio file or a video.")
    return path


# ---------------------------------------------------------------- transcription

def _r(seconds):
    return round(float(seconds), 3)


def _srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(h, m, s, ms)


def transcribe(folder, job):
    from faster_whisper import WhisperModel

    source = source_of(job)
    language = str(job["input"].get("language") or "auto")
    say(progress=0.02, message="Reading the sound")
    audio = _decode(source, rate=16000, mono=True)[0][0]   # a video's sound too
    total = max(len(audio) / 16000, 0.001)
    where = device()
    say(progress=0.05, message="Loading the speech model ({}, {})".format(WHISPER_MODEL, where))
    model = WhisperModel(WHISPER_MODEL, device=where, compute_type="int8_float16" if where == "cuda" else "int8",
                         download_root=job.get("models_dir") or None)
    pieces, info = model.transcribe(audio, language=None if language == "auto" else language, word_timestamps=True,
                                    vad_filter=True, beam_size=5)
    speaker = "SPEAKER_00"
    segments, words = [], []
    for piece in pieces:   # made as they are read: progress is how far into the sound it is
        text = piece.text.strip()
        if not text:
            continue
        segments.append({"start": _r(piece.start), "end": _r(piece.end), "speaker": speaker, "text": text})
        for w in piece.words or []:
            words.append({"start": _r(w.start), "end": _r(w.end), "word": w.word.strip(), "speaker": speaker, "aligned": True})
        say(progress=round(0.1 + 0.85 * min(piece.end / total, 1.0), 3), message="Transcribing: {:.0f} of {:.0f} s".format(piece.end, total))
    result = {"language": info.language, "segments": segments, "words": words}
    (folder / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["{}\n{} --> {}\n[{}] {}\n".format(n, _srt_time(s["start"]), _srt_time(s["end"]), s["speaker"], s["text"])
             for n, s in enumerate(segments, start=1)]
    (folder / "transcript.srt").write_text("\n".join(lines), encoding="utf-8")
    outputs = [{"name": "transcript.json", "mime": "application/json"}, {"name": "transcript.srt", "mime": "application/x-subrip"}]
    note = "Speaker labels are not set up yet: every line is SPEAKER_00." if job["input"].get("speakers") else ""
    say(done=True, outputs=outputs, message=note)


# ---------------------------------------------------------------- voice separation

def _decode(path, rate=None, mono=False):
    """(samples as float32 [channels, n], sample rate) of a file's sound, read with PyAV (any audio file or video): at
    its own rate and channels, or at `rate` and in mono when asked (what faster-whisper takes: 16 kHz mono)."""
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("The file has no sound.")
        rate = rate or stream.codec_context.sample_rate
        layout = "mono" if mono or (stream.codec_context.channels or 1) < 2 else "stereo"
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        parts = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                parts.append(out.to_ndarray())
        for out in resampler.resample(None):
            parts.append(out.to_ndarray())
    if not parts:
        raise ValueError("The file's sound is empty.")
    return np.concatenate(parts, axis=1).astype("float32"), rate


def separate_voice(folder, job):
    import numpy as np
    import soundfile
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from torchaudio.functional import resample

    say(progress=0.02, message="Reading the sound")
    samples, rate = _decode(source_of(job))
    channels, length = samples.shape
    where = device()
    say(progress=0.08, message="Loading the separation model ({}, {})".format(DEMUCS_MODEL, where))
    if job.get("models_dir"):
        torch.hub.set_dir(str(Path(job["models_dir"]) / "torch"))
    model = get_model(DEMUCS_MODEL)
    model.eval()
    wav = torch.from_numpy(samples)
    stereo = wav if channels == 2 else wav[:1].repeat(2, 1) if channels == 1 else wav[:2]
    if rate != model.samplerate:
        stereo = resample(stereo, rate, model.samplerate)
    mean, std = stereo.mean(), stereo.std() + 1e-8
    say(progress=0.15, message="Taking the voice out ({:.0f} s of sound)".format(length / rate))
    with torch.no_grad():
        # split: through a long file in the model's own short pieces (about 8 s for htdemucs), so memory stays small
        stems = apply_model(model, ((stereo - mean) / std)[None], device=where, split=True, overlap=0.25, progress=False)[0]
    vocals = stems[model.sources.index("vocals")] * std + mean
    if rate != model.samplerate:
        vocals = resample(vocals, model.samplerate, rate)
    vocals = vocals[:, :length]
    if vocals.shape[1] < length:   # resampling can lose a sample at the end: the voice is exactly the input's length
        vocals = torch.nn.functional.pad(vocals, (0, length - vocals.shape[1]))
    voice = vocals.numpy() if channels == 2 else vocals.mean(0, keepdim=True).numpy() if channels == 1 else \
        np.concatenate([vocals.numpy(), np.zeros((channels - 2, length), dtype="float32")])
    rest = samples - voice   # music and effects: what is left, so voice + music_fx is the input
    say(progress=0.95, message="Saving the two tracks")
    soundfile.write(str(folder / "voice.wav"), voice.T, rate, subtype="FLOAT")
    soundfile.write(str(folder / "music_fx.wav"), rest.T, rate, subtype="FLOAT")
    say(done=True, outputs=[{"name": "voice.wav", "mime": "audio/wav"}, {"name": "music_fx.wav", "mime": "audio/wav"}])


TOOLS = {"transcribe": transcribe, "separate_voice": separate_voice}


def main(argv):
    if argv[1:2] == ["check"]:
        check()
        return 0
    if len(argv) != 3 or argv[1] not in TOOLS:
        say(error="Usage: run.py check | run.py <{}> <job folder>".format("|".join(TOOLS)))
        return 2
    folder = Path(argv[2])
    started = time.time()
    try:
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        TOOLS[argv[1]](folder, job)
    except Exception as error:   # said in words for the studio's job; the details stay in this process's stderr
        import traceback
        traceback.print_exc()
        say(error="{}: {}".format(type(error).__name__, error) if not isinstance(error, ValueError) else str(error))
        return 1
    print("took {:.1f} s".format(time.time() - started), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
