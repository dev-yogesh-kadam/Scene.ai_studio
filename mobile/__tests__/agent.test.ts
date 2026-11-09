jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));

import { collectResults, GO, recount, type Conversation, type Run } from '@/lib/agent';

const run = (over: Partial<Run>): Run => ({ instruction: 'make a fox', reply: '', steps: [], total: 0, state: 'proposed', at: 1, ...over });

describe('GO', () => {
  it('reads "go ahead" and its kin as Approve', () => {
    for (const said of ['approve', 'Go ahead!', 'yes', 'ok.', 'do it', 'Generate']) expect(GO.test(said)).toBe(true);
  });
  it('leaves real messages alone', () => {
    for (const said of ['yes but make it darker', 'go ahead and change shot 2', 'no']) expect(GO.test(said)).toBe(false);
  });
});

describe('recount', () => {
  it('prices the steps not left out', () => {
    const plan = run({ steps: [{ name: 'a', credits: 100 }, { name: 'b', credits: 50, skipped: true }, { name: 'c', credits: 25 }] });
    recount(plan);
    expect(plan.total).toBe(125);
  });
});

describe('collectResults', () => {
  it('gives a step the item its finished job made, once', () => {
    const convo: Conversation = {
      runs: [run({ state: 'approved', steps: [{ name: 'shot 1', job: 'j1' }, { name: 'shot 2', job: 'j2' }] })],
      direction: '',
      folded: 0,
      workflows: [],
    };
    const jobs = [
      { id: 'j1', status: 'done', items: [{ id: 41 }] },
      { id: 'j2', status: 'running', items: [] },
    ];
    expect(collectResults(convo, jobs)).toBe(true);
    expect(convo.runs[0].steps.map((s) => s.made)).toEqual([41, undefined]);
    expect(collectResults(convo, jobs)).toBe(false);
  });
});
