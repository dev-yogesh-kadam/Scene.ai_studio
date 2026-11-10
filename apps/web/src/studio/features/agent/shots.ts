// What can be said about a plan's steps without asking anyone: their takes, the best of them, what they cost, and how
// they read in a few words.

import type { Job, Run, Spent, Step, Take } from './types';

export const MAX_RETAKES = 3; // under "Allow all" a failed shot is made again up to this many times; then the best goes on
export const REVIEW_WITHIN = 24 * 3600 * 1000; // a shot finished longer ago than this is not reviewed when the panel opens
export const REVIEWS_AT_ONCE = 3; // a batch is checked together, a few at a time so the studio's other calls get through
export const KEPT = 60; // how many turns an agent tab keeps
export const RECALLED = 40; // how many earlier turns are sent along (the server keeps the newest that fit its budget)
export const LONG_REPLY = 700; // a reply longer than this is folded to a few lines, with Show more
export const SAVED_ONLY = 3; // turns of a long run in a row that only save their work and go on by themselves
export const OTHER = '\u0000other'; // the pick of a question's card that is the user's own words
/** A message that only says to go ahead: under a plan that waits for approval it approves it. */
export const GO =
  /^\W*(approve|approved|start|go|go ahead|yes|ok|okay|proceed|generate|generate it|make it|do it|run it|confirm)\W*$/i;

/** Every take of a step in the order they were made: the first, the earlier retakes, the newest retake. */
export const takesOf = (step: Step): Take[] => [step, ...(step.earlier || []), ...(step.take2 ? [step.take2] : [])];
export const retakesOf = (step: Step) => takesOf(step).length - 1;

/** How far a checked take is from what was asked: major faults count most, then minor; unchecked is worst. */
const faults = (take: Take) => {
  if (!take.review) return Infinity;
  const count = (level: string) => (take.review?.checks || []).filter((c) => c.level === level).length;
  return (take.review.passed ? 0 : 1000 * Math.max(1, count('major'))) + count('minor');
};

/** The best take made: the fewest faults, the newer of two as good. */
export const bestTake = (step: Step) =>
  takesOf(step)
    .filter((t) => t.made)
    .reduce<Take | null>((best, t) => (!best || faults(t) <= faults(best) ? t : best), null);

/** Whether a step has a line under its grid: a retake being made, or takes to pick from. */
export const reviewShown = (step: Step) =>
  (!!step.take2 && !step.take2.made) || takesOf(step).filter((t) => t.made).length > 1;

/** The pictures and clips a plan generates: what the agent checks. */
export const shotsOf = (run: Run) =>
  run.steps.filter((s) => !s.skipped && s.settings && (s.kind === 'image' || s.kind === 'video'));

/** The take the cut and the next stage use: the first, or the retake when the user (or a failed review) chose it.
 *  step.chosen is the number of a take (1 the first); with none, a shot that failed goes on with its newest take. */
export const usedTake = (step: Step): Take => {
  const all = takesOf(step);
  const picked = step.chosen ? all[step.chosen - 1] : undefined;
  if (picked && picked.made) return picked;
  const newest = [...all].reverse().find((t) => t.made);
  return step.chosen == null && step.review && !step.review.passed && newest ? newest : step;
};

/** What one conversation (or one turn) has spent, by what it made. A job that failed gave its credits back. */
export function spentBy(runs: Run[], jobs: Job[] = []): Spent {
  const spent: Spent = { video: 0, image: 0, audio: 0, llm: 0, total: 0 };
  const refunded = new Set(jobs.filter((j) => j.status === 'failed' || j.status === 'cancelled').map((j) => j.id));
  for (const run of runs || []) {
    const llm = (run.llm && run.llm.credits) || 0; // what the messages to the agent's model cost
    spent.llm += llm;
    spent.total += llm;
    for (const step of run.steps || []) {
      const takes: [Take | null | undefined, number | undefined][] = [
        [step, step.credits],
        ...(step.earlier || []).map((t): [Take, number | undefined] => [t, t.credits]),
        [step.take2, step.take2 ? step.take2.credits || step.retake?.credits : undefined],
      ];
      for (const [take, credits] of takes) {
        if (!take || !take.job || refunded.has(take.job) || !credits) continue;
        const kind = step.kind === 'image' || step.kind === 'audio' ? step.kind : 'video'; // motion and edits are videos
        spent[kind] += credits;
        spent.total += credits;
      }
    }
  }
  return spent;
}

/** A length as the card shows it: whole seconds as they are, a clip timed to its frames to two decimals. */
export const secs = (d: number) => (Number.isInteger(Number(d)) ? `${d}s` : `${Number(d).toFixed(2)}s`);
export const SHAPES = [
  { id: 'landscape', label: '16:9' },
  { id: 'square', label: '1:1' },
  { id: 'portrait', label: '9:16' },
];
const SHAPE_NAMES: Record<string, string> = { landscape: '16:9', portrait: '9:16', square: '1:1' };
const CAMERA_WORDS: Record<string, string> = {
  ECU: 'extreme close-up',
  CU: 'close-up',
  MCU: 'medium close-up',
  MS: 'medium shot',
  WS: 'wide shot',
  EWS: 'extreme wide',
  eye: 'eye level',
  low: 'low angle',
  high: 'high angle',
  top: 'top-down',
  OTS: 'over the shoulder',
};
const cameraOf = (step: Step) =>
  step.camera
    ? [CAMERA_WORDS[step.camera.shot_size ?? ''], CAMERA_WORDS[step.camera.angle ?? ''], step.camera.move]
        .filter(Boolean)
        .join(' · ')
    : '';

/** The settings of a step as short words: model, shape, size, length, clips, quality. */
export const tagsOf = (step: Step) => {
  const current = step.current || {};
  return (
    step.settings
      ? [
          step.workflow_title,
          cameraOf(step),
          current.orientation && SHAPE_NAMES[current.orientation],
          current.resolution && current.resolution + 'p',
          current.duration && secs(current.duration),
          (step.settings.clips ?? 0) > 1 && '× ' + step.settings.clips + ' clips',
          step.settings.options?.quality && step.settings.options.quality + ' quality',
          step.shot_number && 'Shot ' + step.shot_number,
          step.variation && `Variation ${step.variation.n} of ${step.variation.of}`,
          step.board && 'on ' + step.board,
        ]
      : [step.workflow_title, step.facts]
  ).filter((t): t is string => !!t);
};
export const linksOf = (step: Step) =>
  [step.start && 'starts on ' + step.start.name, step.after && `continues step ${step.after.step + 1}`].filter(
    (t): t is string => !!t,
  );

/** What a plan makes, in words: "5 images", "1 video", "4 generations" when the kinds are mixed. */
export function planCount(run: Run, kindOnly = false) {
  const kept = run.steps.filter((s) => !s.skipped);
  const kinds = new Set(kept.map((s) => (s.assemble || s.motion ? 'video' : s.sound ? 'audio' : s.kind || 'video')));
  const names: Record<string, string> = { image: 'image', video: 'video', audio: 'sound' };
  const kind = kinds.size === 1 ? names[[...kinds][0]] || '' : '';
  if (kindOnly) return kind;
  const n = kept.length;
  return `${n} ${kind ? (kind === 'sound' ? (n === 1 ? 'sound' : 'sounds') : kind + (n === 1 ? '' : 's')) : n === 1 ? 'generation' : 'generations'}`;
}

export const recount = (run: Run) => {
  run.total = run.steps.reduce((sum, s) => sum + (s.skipped ? 0 : s.credits || 0), 0);
};

/** The questions of a turn, one or several, as one list. */
export const questionsOf = (run: Run) => (run.question ? [run.question] : run.questions || []);

/** The shots of a plan whose check found a problem and that wait for the user's word. */
export const flagged = (run: Run) =>
  shotsOf(run).filter((s) => s.review && !s.review.passed && !s.take2 && !s.kept && s.retake);

/** The video shots of a plan that can be drawn as stills first. */
export const eligible = (run: Run) =>
  run.steps.filter((s) => s.proposal && s.shot_id && s.kind === 'video' && !s.skipped && s.settings);

/** "6s", "1m 20s". */
export const span = (seconds: number | undefined | null) => {
  const s = Math.max(0, Math.round(seconds || 0));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
};
/** "0:04", the place of a frame in a clip. */
export const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
