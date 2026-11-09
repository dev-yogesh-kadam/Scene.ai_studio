id: minimax-h3
title: MiniMax H3
workflows: ^video/h3_
length: 150 to 280 words: the blocks carry the scene, the shots stay one or two beats for a clip of one action
limit: 450
---
H3 reads a long prompt in labelled blocks. Write these blocks in this order, each label on its own line, and leave out
a block only when the shot has nothing for it:

GOAL
One line: what happens, who, where.

ASSETS
One line per reference the step fills, one subject and one job each, named the way the workflow's labels or
prompt_tips say ("the main character", "the background", or <Picture 2> on H3 Chunk): a person "face, hair and
clothing only"; a place "layout and light only, ignore any people in it"; a prop "shape, material and colour only";
a voice "the voice of the main character only"; a motion video "camera movement and pacing only", never its people,
place or look. Two pictures of one person (H3 All in One's "same person, other angle", a sheet and a close face) are
one line: "both pictures show the main character, one person"; one person's pictures never make two people. A frame
taken from a clip is never a person's reference: their identity comes from their sheet or portrait. Never name a
reference the step does not fill.

SCENE
The layout (what is in the foreground, the middle and the background), the light source and its direction, the time
of day, the weather, the ambience, and the music bed or "no music".

OPENING
The first frame: who is where, facing which way, looking at what, holding what. A clip that carries on from another
says that clip's end state here as present fact; never "previous", "earlier" or a clip number.

SHOTS
Timed beats that cover the whole length:
[0-2s] medium close-up, 35mm, eye level → she sets the cup down and looks up → she says: "You came back." → slow push in
[2-5s] ...
A clip of one action has one or two beats, not more: the action itself, in plain physical words (what moves where:
"he kicks the ball into the wall; it rebounds along the ground and he stops it under his sole"), and its finish.
Splitting one action into many timed pieces makes H3 lose the action. One main moving subject. The camera in plain
film words ("slow push in", "locked-off tripod shot", "handheld, following him"), and it keeps the whole action in
frame to the end: hands, feet, the ball, what is handed over; a push in that would crop them stays wider. Acting as
what shows: "her jaw tightens", not "she is angry"; no eye contact with the camera or posed endings unless asked.
A clip is one continuous shot unless the user asked for cuts: the first beat sets the framing and lens, and later
beats change it only by moving the camera ("the push in ends on a medium close-up"). A new framing or lens in a beat
is a hard cut, so write one only for a cut that was asked for, and then say "Cut to".
A clip packed from a plan (a skill's clips) has the plan's cuts, and they count as asked for: each planned shot after
the first opens with "Cut to", with its keyframe when the workflow takes one per shot.

STYLE
The look, once: live action or the animation style, the grade, the texture, the lens or film feel.

END STATE
Where everyone ends, who holds what, where the camera ends.

LOCKS
What must stay: the identity words, the wardrobe, counts ("two cups"), screen direction, and short "No ..." lines
beside what they protect: "No hard cuts. No on-screen text. No extra people." H3 has no negative prompt; this is it.

Rules:
- Identity in words, short and the same in every clip of the piece, word for word: age, build, the features that tell
  people apart, what the action needs. Logos, small text on things and key colours are said in words too.
- Sound is always on. Spoken words go in quotes, tied to the speaker: the old man says: "Sign here." A clip with no
  speech or music says "No dialogue. No music." in LOCKS.
- With a voice track and lips following it, say who speaks when: "the main character speaks 'line' at 3.2-5.0 s;
  nobody else's lips move". The track is used as recorded, word for word ("Use the voice track exactly as recorded."
  in LOCKS), and no voice sample goes beside it: the recording's voice is the voice.
- A shot that starts on a picture kept exactly (first-frame mode): ASSETS says only that the picture is the first
  frame; SHOTS describe motion and camera only, never what the frame already shows, and the first beat keeps the
  picture's own framing: one it does not have (a close-up of a wide picture) makes a hard cut away from it.
- No shape, length, resolution or frame-rate words anywhere.
