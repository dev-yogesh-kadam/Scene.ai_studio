id: ffmpeg-recipes
title: ffmpeg recipes — your own commands with the ffmpeg tool
version: 2
desc: Load before writing a command for the ffmpeg tool, and again when one fails: the rules of its folder, quoting, and tested commands for cutting, joining, fitting, grading, effects, sound, captions and measuring.
words: (?!)
guide: true
---
The ffmpeg tool runs a command you write with ffmpeg 9 on this machine. It is for work on media that already
exists: cut, join, crossfade, fit to a shape, grade, speed, punch in, shake, freeze, lay one thing over another, mix
and duck sound, burn captions, make stills and GIFs, and measure. It makes nothing new and knows nothing of what is in
the picture: look at a clip first, then cut it. It is free and quick (most commands take a second or two).

Use the film tool's own ops when one does exactly the job (they are tested and keep their findings in the run):
subtitles for captions from lines, film for shots on the master audio, beat_cut, multicam, composite, keyframes,
board, gif, audio_check. Use this tool for everything else, and for a look those ops can't give. Words that need design
(a title, a lower third, a card) are an html page (the html-scenes skill), not drawtext.

## The job

The ffmpeg tool's fields:
```
{"argv": ["-i", "a.mp4", "-vf", "scale=1080:-2", "-c:v", "libx264", "-crf", "18", "out.mp4"],
 "inputs": [{"name": "a.mp4", "item": 4211}],
 "sidecars": [{"name": "caps.ass", "content": "..."}],
 "outputs": [{"name": "out.mp4"}],
 "timeout": 300, "reason": "one line on what it is for"}
```
- argv is the words after "ffmpeg", one string each, run as they are: no shell, so no quotes around a word, no pipes,
  no && and no redirects. A whole filter graph is one word.
- The command runs in a folder of its own that holds only: each input, copied in under its name; each sidecar, written
  under its name; and the studio's fonts (Poppins-Regular.ttf, Poppins-SemiBold.ttf, Poppins-Bold.ttf,
  Poppins-ExtraBold.ttf, Poppins-Black.ttf, Anton-Regular.ttf, BebasNeue-Regular.ttf, ArchivoBlack-Regular.ttf,
  Bangers-Regular.ttf, NotoSansDevanagari.ttf). Name every file by its bare name. Nothing outside the folder exists for
  the command: no path with a folder, no drive, no "..", no URL or protocol (http:, concat:, pipe:...), no device or
  screen capture (-f dshow, gdigrab, ddagrab), no movie or zmq filter. ffmpeg opens files only.
- inputs: at most 10, any library item (video, picture, sound, text) by its id, under a bare name with its type
  (a.mp4, logo.png, vo.wav). A job may have none (one that makes a tone or silence with -f lavfi).
- sidecars: at most 5 small text files (.txt, .ffconcat, .ass, .srt, .vtt, .cube, .3dl, .csv), 200,000 characters
  each: a subtitle file, a concat list, a long filter graph (-filter_complex_script graph.txt), a colour LUT.
- outputs: at most 4, each named as its own word in argv, each a .mp4 .mov .webm .mkv .png .jpg .webp .gif .wav .mp3
  .m4a .aac .flac .ogg .opus .srt .ass .vtt .txt .json or .csv. Each comes back as a library id, filed as what it is.
  With no outputs (a command ending "-f", "null", "-"), you get what ffmpeg said: that is how you measure.
- Names are unique across inputs, sidecars and outputs. A numbered sequence (frame_%03d.png) is not an output: make a
  contact sheet, or one job per frame.
- timeout: 30 to 600 seconds, 300 when not given. A long re-encode needs more; split very long work into jobs.
- The result gives each file's id, kind, duration and size, and "log": the end of what ffmpeg said. Look at a video or
  picture made before you build on it.

The settings are JSON text, so a backslash inside a word is written \\ there (one backslash reaches ffmpeg).

## Quoting inside a filter

- A filter's options are separated by ":", filters by ",", chains by ";". Inside a value that holds any of : , ; [ ]
  (an expression, a text, an enable=), put the value in single quotes. Inside the quotes, write a ":" in a text as \:
  ("drawtext=text='Scene 4\: Rooftop'"); a "," or ";" inside quotes needs nothing.
- Without the quotes, an expression's commas end the filter: enable=between(t,2,6) fails, enable='between(t,2,6)'
  works.
- Sizes are WxH in a source (color=s=1080x1920), W:H in scale and crop.
- Times in trim, atrim, -ss, -t and -to are plain numbers: work the sum out and write it (atrim=start=4:end=12).
  Expressions work in the options that take them: positions and sizes of crop, pad, overlay, scale with eval=frame,
  drawtext x and y, setpts, enable.
- Each filter has its own time variables: t (seconds) in most; n (frame number) in crop, overlay and scale; on
  (output frame) and zoom in zoompan. An expression must stay valid on every frame to the last: wrap a ramp in
  min(), max() or clip().
- A long graph goes in a sidecar: "-filter_complex_script", "graph.txt" (a .txt sidecar holding the graph as it is).

## Encoding

- Video for the studio and for posting: "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
  "-movflags", "+faststart". crf 16 for a master that is cut again, 20 to 23 for a small preview.
- Faster on this machine's NVIDIA card: "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-pix_fmt", "yuv420p".
- Sound: "-c:a", "aac", "-b:a", "192k", "-ar", "48000". A sound file kept for more work: "-c:a", "pcm_s16le" in a .wav.
- A see-through overlay: "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "32" in a .webm.
- "-c", "copy" changes nothing in the picture and is instant, but cuts only on keyframes and joins only clips made
  alike. When in doubt, encode.
- The studio's shots are 24 fps. Keep a film at 24 ("fps=24" in the graph) so nothing judders.

## Cut and join

**Look first.** ["-i", "a.mp4", "-f", "null", "-"] with no outputs: the log gives its streams (codec, WxH, fps, sound
or none) and its length.

**Trim, frame-exact.** ["-ss", "2.5", "-i", "a.mp4", "-t", "3.2", "-c:v", "libx264", "-crf", "18", "-pix_fmt",
"yuv420p", "-c:a", "aac", "cut.mp4"]. -ss before -i seeks fast and, encoded, is exact.

**Join clips made alike** (the same size, fps and codec: takes of one run). A sidecar list.txt:
"ffconcat version 1.0\nfile 'a.mp4'\nfile 'b.mp4'\nfile 'c.mp4'\n", every clip also an input, then
["-f", "concat", "-i", "list.txt", "-c", "copy", "joined.mp4"]. Never add "-safe 0": the bare names are safe.

**Join clips that differ** (sizes, rates, one without sound): fit each, then concat:
```
[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p[v0];
[1:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p[v1];
[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];
[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]
```
then "-map", "[v]", "-map", "[a]". A clip with no sound gets silence: add ["-f", "lavfi", "-t", "<its length>", "-i",
"anullsrc=r=48000:cl=stereo"] as an input and use that as its sound.

**Crossfade or a transition.** xfade needs both sides the same size, fps, pixel format and time base, so end each
chain with ",fps=24,format=yuv420p,settb=AVTB". offset is where the transition starts: the first clip's length minus
the transition's length; for a third clip, the length of what is joined so far minus the next transition.
```
[v0][v1]xfade=transition=fade:duration=0.5:offset=4.5[v];[a0][a1]acrossfade=d=0.5[a]
```
Transitions: fade, fadeblack, fadewhite, dissolve, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright,
slideup, slidedown, smoothleft, smoothright, smoothup, smoothdown, circleopen, circleclose, radial, zoomin, hblur,
pixelize, coverleft, coverright, revealleft, revealright, squeezeh, squeezev, diagtl, diagbr. A film mostly cuts; a
fade marks time passing or a new scene; the showy ones belong in a reel, sparingly.

## Fit a shape

- **Crop 16:9 to 9:16** at a point (x from 0 left to 1 right): "crop=ih*9/16:ih:(iw-ih*9/16)*0.5:0,scale=1080:1920".
  The film tool's reframe op does this too.
- **Keep it whole on a blurred fill** (16:9 into 9:16, nothing cut, nothing invented):
  ```
  [0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.08[bg];
  [b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]
  ```
- **Bars** (letterbox to 2.39:1 inside the frame): "drawbox=x=0:y=0:w=iw:h=(ih-iw/2.39)/2:c=black:t=fill,
  drawbox=x=0:y=ih-(ih-iw/2.39)/2:w=iw:h=(ih-iw/2.39)/2:c=black:t=fill".

## Effects that make an edit feel cut by hand

- **Punch-in** (a cut to closer, at 1 s to 2.5 s): scale up per frame, then crop back to the frame. An animated crop
  size does nothing (crop reads its size once):
  "scale=w='iw*if(between(t,1,2.5),1.3,1)':h='ih*if(between(t,1,2.5),1.3,1)':eval=frame,crop=1920:1080".
- **Slow push in** on a clip: "zoompan=z='min(1+0.0025*on,1.25)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':
  s=1920x1080:fps=24". d=1 keeps one frame out for each frame in.
- **Ken Burns on a still**: ["-loop", "1", "-framerate", "24", "-t", "4", "-i", "still.png", "-vf",
  "scale=4320:-2,zoompan=z='1+0.12*on/96':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=24,format=yuv420p",
  ...]. Scaling up first keeps the move smooth; 96 is the frames in 4 s.
- **Shake** (1 s to 1.5 s): "crop=iw-48:ih-48:x='24+if(between(t,1,1.5),20*sin(t*70),0)':y='24+if(between(t,1,1.5),
  16*cos(t*53),0)',scale=1920:1080".
- **Flash** on a hit (2 s): "drawbox=c=white@0.85:t=fill:enable='between(t,2,2.08)'". Two or three frames is a flash.
- **Freeze** at 2 s for 1 s, then on:
  "[0:v]trim=0:2,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=1[f];[0:v]trim=2,setpts=PTS-STARTPTS[r];
  [f][r]concat=n=2:v=1:a=0[v]" (the sound, if kept, needs the same second of silence: adelay or apad).
- **Speed**: twice as fast "setpts=PTS/2" with "atempo=2"; half speed "setpts=2*PTS" with "atempo=0.5". **A ramp**:
  trim the clip into parts, give each its own setpts ("setpts=2.5*(PTS-STARTPTS)" slow, "setpts=0.6*(PTS-STARTPTS)"
  fast), concat them, then "fps=24".
- **Grade**: "eq=contrast=1.08:saturation=1.12" for punch; warm it with "colorbalance=rs=0.04:bs=-0.05:rh=0.03:
  bh=-0.03"; "curves=preset=medium_contrast"; "vignette=PI/5"; grain "noise=alls=6:allf=t". A LUT: a .cube sidecar and
  "lut3d=look.cube". Grade every shot of a scene with the same filter, or it flickers between shots.
- **Fades**: "fade=t=in:st=0:d=0.5,fade=t=out:st=<length-0.5>:d=0.5", sound "afade=t=in:d=0.3,afade=t=out:st=<..>:d=0.8".

## Laying one thing over another

- **A see-through clip** (an html page made as webm, a lower third): decode it with its alpha, which means
  "-c:v", "libvpx-vp9" BEFORE its "-i": ["-i", "bg.mp4", "-c:v", "libvpx-vp9", "-i", "lt.webm", "-filter_complex",
  "[0:v][1:v]overlay=0:0:shortest=1,format=yuv420p[v]", "-map", "[v]", "-map", "0:a?", ...]. Without that word the
  overlay comes out on black. To start it at 3 s: "[1:v]setpts=PTS-STARTPTS+3/TB[o];[0:v][o]overlay=0:0:eof_action=pass".
- **A logo** (a PNG with transparency) top right: "[1:v]scale=180:-1[l];[0:v][l]overlay=W-w-60:60".
- **Picture in picture**: "[1:v]scale=360:-2[p];[0:v][p]overlay=W-w-40:H-h-40:shortest=1".

## Sound

- **Take the sound out**: ["-i", "a.mp4", "-vn", "-c:a", "pcm_s16le", "sound.wav"].
- **Replace the sound**: ["-i", "a.mp4", "-i", "vo.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
  "-b:a", "192k", "-shortest", "out.mp4"].
- **A voice over music, the music ducked under it** (0 the voice, 1 the music):
  ```
  [0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key];
  [1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.35[m];
  [m][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=350[bed];
  [vo][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]
  ```
  Music under a film's own dialogue: the same, with the film's sound as the key and as the voice.
- **Loudness for posting** (-14 LUFS, peaks under -1.5 dB): one pass "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000".
  Exact, in two jobs: first ["-i", "a.mp4", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null",
  "-"] and read input_i, input_tp, input_lra, input_thresh and target_offset from the log; then
  "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=..:measured_TP=..:measured_LRA=..:measured_thresh=..:offset=..:linear=true,
  aresample=48000". Level the finished cut once, at the end, never each shot.
- **Silence** to fill: a second input ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] with "-shortest"; or "apad"
  on a sound that ends early.
- A sound effect at 3.2 s: "[1:a]adelay=3200|3200[s];[0:a][s]amix=inputs=2:duration=first:normalize=0[a]".

## Words on the picture

**Captions: an .ass sidecar** and "ass=caps.ass:fontsdir=." (fontsdir=. finds the studio's fonts in the folder).
```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Poppins,78,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,0,2,90,90,560,1
Style: Hi,Noto Sans Devanagari,78,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,0,2,90,90,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.40,Cap,,0,0,0,,WAIT... {\c&H0000D7FF&}WHAT?
Dialogue: 0,0:00:01.40,0:00:02.80,Hi,,0,0,0,,यह काम करता है
```
- Colours are &HAABBGGRR: blue, green, red, in that order (&H0000D7FF is gold), AA 00 solid to FF clear.
- PlayResX/Y the video's size, so sizes and margins are in its pixels. Alignment 2 is bottom centre, 5 the middle, 8
  the top; MarginV lifts it (560 on 9:16 keeps it above the app's own bar).
- A word lit as it is said: {\k40} before each word (hundredths of a second) with the SecondaryColour as the colour
  before it is said; or one Dialogue line a word, each with that word in {\c&H..&}.
- Hindi and other Devanagari: a style whose font is Noto Sans Devanagari, on every Hindi line. A Latin font that falls
  back to it breaks the joined letters into dotted circles.
- Fonts in the folder, by the names a style uses: Poppins (Regular, SemiBold, Bold, ExtraBold, Black), Anton,
  Bebas Neue, Archivo Black, Bangers, Noto Sans Devanagari.
- An .srt works too ("subtitles=caps.srt:fontsdir=.:force_style='Fontname=Poppins,Fontsize=22,Outline=2'"), with less
  control.

**A short label** (a slate, a timestamp, a watermark): "drawtext=fontfile=Poppins-Bold.ttf:text='Take 3':fontsize=48:
fontcolor=white:borderw=3:bordercolor=black:x=(w-tw)/2:y=h-th-120". Designed words are an html page instead.

## Stills and loops

- **One frame** at 2.5 s: ["-ss", "2.5", "-i", "a.mp4", "-frames:v", "1", "-update", "1", "f.png"]. **The last**:
  ["-sseof", "-0.1", "-i", "a.mp4", "-frames:v", "1", "-update", "1", "last.png"].
- **A contact sheet** (a frame every half second, 4 across): "fps=2,scale=320:-2,tile=4x3" with "-frames:v", "1".
- **A GIF**: "fps=12,scale=480:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=
  bayer:bayer_scale=4" as -filter_complex, with "-loop", "0".
- **Vector shapes** drawn on a frame (ffmpeg 9): "drawvg=s='circle 960 540 120 setcolor red@0.6 fill'".

## Measuring (no outputs: read the log)

- Loudness: "-af", "ebur128=peak=true:framelog=quiet" (I is the loudness in LUFS, LRA its range, Peak the true peak).
- Quiet stretches: "silencedetect=n=-45dB:d=0.4" (silence_start and silence_end).
- Black or frozen picture: "blackdetect=d=0.1:pix_th=0.1", "freezedetect=n=0.003:d=0.5".
- Cuts: "scdet=threshold=10" (the film tool's shots op is easier and keeps them).
- Bars or borders: "cropdetect" (the last crop= line is the picture's real box).
Then end the command with "-f", "null", "-".

## When a job fails

- Refused before it runs: the reason names each problem (a word that names a file outside the folder, a file not
  declared, a protocol). Fix all and send again.
- "No such filter: 'X'": a comma ended an expression early, or a name is misspelt; quote the expression.
- "No option name near ...": a ":" inside a text or expression that is not escaped or quoted.
- "Undefined constant or missing '(' in ...": a variable another filter has (n in zoompan, on in crop).
- "Error while filtering: Invalid argument" partway through: an expression went out of range near the end; clamp it.
- "Stream specifier ... matches no streams" / "does not contain any stream": the input has no sound ("0:a?" maps it
  only when there is one), or a label is used twice or never.
- "First input link ... parameters do not match" (xfade, concat): sizes, fps, pixel formats or time bases differ;
  fit each chain the same way and end it with fps=24,format=yuv420p,settb=AVTB.
- Overlay of a webm comes out on black: "-c:v", "libvpx-vp9" was not before its "-i".
- Finished without writing an output: the output's name in argv differs from the one declared.
- Took too long: give it a longer timeout, encode with h264_nvenc, or split the work.
