// What the landing page says: what can be made, the steps, the uses, and the questions before signing up.

// What can be made, with the models that make it. Kept in step with workflows/ (see docs/HANDOVER.md, Workflows).
export const KIT: string[][] = [
  [
    'Video',
    'Clips with sound',
    'MiniMax H3 · LTX-2.5',
    'Clips of 5 to 15 seconds from a prompt and up to eight references: a character, an outfit, a place, a motion to copy, a voice. Chain clips into longer scenes that pick up where the last one ended.',
  ],
  [
    'People',
    'Talking and moving',
    'Talking Head · Lip Sync · Wan Animate 2',
    'A portrait that speaks a voice track, a clip whose lips meet new words, a character doing the moves of a video you give it.',
  ],
  [
    'Restyle',
    'A new look, the same motion',
    'LTX-2.3 IC-LoRA · Wan 2.2 Fun · Wan VACE',
    'Keep how a video moves and change how it looks, or widen it into a new shape with the edges filled in.',
  ],
  [
    'Images',
    'Stills and posters',
    'FLUX.2 · FLUX 3 Klein · Qwen Image 2.1 · Hunyuan 2.1 · Krea 2',
    'Stills from a prompt and up to four reference pictures, so a character looks the same in every one.',
  ],
  [
    'Sound',
    'Songs, voices and words',
    'MiniMax Music 3 · Separate voice · Transcribe',
    'Songs from 30 seconds to 5 minutes, with your lyrics or without; a voice lifted out of the music; a transcript with times and speakers.',
  ],
  [
    'Titles',
    'Motion graphics',
    'Drawn in the studio',
    'Title cards, lower thirds and whole videos of animated words, written from a sentence and editable scene by scene.',
  ],
  ['Finish', 'Upscale', 'SeedVR2', 'A finished video made larger and sharper, up to four times its size.'],
];

// Your first video, as the guide tells it (docs/guide.md, section 2).
export const STEPS: string[][] = [
  [
    'Say what you want',
    'Type the shot, or tell the agent about the whole film. Add reference pictures if you have them.',
  ],
  ['Approve the plan', 'Every step comes with its model and its price. Nothing runs until you press Approve.'],
  [
    'Every take is checked',
    'Wrong face, broken hands, the wrong place: the take is flagged and can be retaken with a new approach.',
  ],
  ['Cut and export', 'The agent puts the shots in order, music under them, titles on top. One finished video.'],
];

// What people make with it, each with a prompt to start from. The picture is one of the drawn scenes.
export const USES: [string, string, string, boolean?][] = [
  [
    'rooftop',
    'Ads and product videos',
    'A 20 second ad for our sneaker drop. Rooftop at golden hour, the same runner in every shot.',
  ],
  [
    'neon',
    'Reels, Shorts and TikToks',
    'A 9:16 Reel: a street food vendor in Mumbai at night, neon, quick cuts on the beat.',
  ],
  [
    'desert',
    'Short films from a script',
    'Turn my script into a 1 minute short. Two travellers, an old jeep, a desert at noon.',
  ],
  [
    'deep',
    'Explainers from an article',
    'Make a 45 second vertical explainer of this article, with a voiceover and captions.',
  ],
  [
    'rooftop',
    'Talking heads and dialogue',
    'My founder portrait says this welcome line, lips in time, a soft office behind her.',
    true,
  ],
  ['neon', 'Music videos', 'A 30 second synthwave track and a neon city drive cut to it.', true],
  ['desert', 'A new look for your video', 'Keep how my clip moves, make it look like a hand-painted film.', true],
  ['deep', 'Titles and motion graphics', 'An intro card and lower thirds for my podcast, clean and bold.', true],
];

// What the agent does besides planning (docs/history/agent-features-2026-11.md, docs/guide.md section 11).
export const AGENT: string[] = [
  'Plans whole films, ads and Reels',
  'Prices every step first',
  'Looks at every take',
  'Retakes a failed shot',
  'Makes variations side by side',
  'Researches on the web, with sources',
  'Explains the craft when you ask',
  'Asks a second opinion',
];

// After the take: the rest of the studio.
export const BENCH: string[][] = [
  [
    'Canvas',
    'One row per shot',
    'Results land in the row of their shot; takes stack newest on top, so the board reads like a shot list.',
  ],
  [
    'Final cut',
    'A finished film',
    'Trim, order, add music. Fades, music ducked under speech and even loudness, in one export.',
  ],
  [
    'Long runs',
    'Films made step by step',
    'A script becomes a film over many turns. It carries on by itself, and another tab or teammate can pick it up.',
  ],
  [
    'Shape',
    'Any screen',
    'A video cropped to 9:16, 1:1, 4:5 or 16:9 around what matters, or widened with the new space filled in.',
  ],
  [
    'Free',
    'Edits on the house',
    'Trims, joins, subtitles burned in, retimes to a voice track and proof sheets run on the studio, at no cost.',
  ],
  [
    'Teams',
    'Projects with people',
    'Invite members to a project with a role, share what you made, and keep one memory for the whole team.',
  ],
];

// Questions before signing up, answered from what the studio does.
export const FAQ: string[][] = [
  [
    'Do I need to know AI tools or own a GPU?',
    'No. The studio runs the models for you. You write, look and choose; there is nothing to install or wire up.',
  ],
  [
    'Will my character look the same from shot to shot?',
    'That is what NeuralCore is for. Keep a face, an outfit, a place or a voice once, and every later shot of it uses that picture.',
  ],
  [
    'What does it cost?',
    'Credits, for what you make: a set price per picture, a price per second for video and music. You see the price before you press Generate.',
  ],
  [
    'What if a take comes out wrong?',
    'A job that fails or is cancelled gives its credits back. The agent checks each take it planned and offers a retake when something is off.',
  ],
  [
    'Can my team work in the same project?',
    'Yes. A project has members with roles, its own canvases and memory, so anyone on it can carry on the work.',
  ],
];

// Four takes of one shot for the take report: what each was, and the one that was kept.
export const TAKES: string[][] = [
  ['rooftop', 'Take 1', '6.0 s', 'Rejected · face', 'dull'],
  ['rooftop', 'Take 2', '6.0 s', 'Soft focus', 'soft'],
  ['rooftop', 'Take 3', '6.0 s', 'Kept', 'kept'],
  ['neon', 'Take 4', '5.0 s', 'New seed', ''],
];

// NeuralCore as the panel shows it: the cast, places and voices kept once.
export const CORE: [string, string[][]][] = [
  [
    'Cast',
    [
      ['rooftop', 'Meera', 'Yellow raincoat · in 14 shots'],
      ['neon', 'Raghav', 'Denim jacket · in 6 shots'],
    ],
  ],
  [
    'Places',
    [
      ['neon', 'Night market', 'Wet street, neon signs'],
      ['rooftop', 'Rooftop', 'Golden hour, skyline'],
    ],
  ],
  ['Voices', [['deep', 'Meera · warm', 'Hindi and English']]],
];
