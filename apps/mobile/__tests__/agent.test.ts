jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));

import { applyPlan, approvePlan, collectResults, GO, recount, running, type Conversation, type Run } from '@/lib/agent';

const run = (over: Partial<Run>): Run => ({
  instruction: 'make a fox',
  reply: '',
  steps: [],
  total: 0,
  state: 'proposed',
  at: 1,
  ...over,
});

describe('GO', () => {
  it('reads "go ahead" and its kin as Approve', () => {
    for (const said of ['approve', 'Go ahead!', 'yes', 'ok.', 'do it', 'Generate']) expect(GO.test(said)).toBe(true);
  });
  it('leaves real messages alone', () => {
    for (const said of ['yes but make it darker', 'go ahead and change shot 2', 'no'])
      expect(GO.test(said)).toBe(false);
  });
});

describe('recount', () => {
  it('prices the steps not left out', () => {
    const plan = run({
      steps: [
        { name: 'a', credits: 100 },
        { name: 'b', credits: 50, skipped: true },
        { name: 'c', credits: 25 },
      ],
    });
    recount(plan);
    expect(plan.total).toBe(125);
  });
});

describe('collectResults', () => {
  it('gives a step the item its finished job made, once', () => {
    const convo: Conversation = {
      runs: [
        run({
          state: 'approved',
          steps: [
            { name: 'shot 1', job: 'j1' },
            { name: 'shot 2', job: 'j2' },
          ],
        }),
      ],
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

describe('plans the studio carries out', () => {
  const { fetch } = jest.requireMock('expo/fetch') as { fetch: jest.Mock };
  const answer = (body: unknown) => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  });

  it('approves through the plan routes: made once, then started; a plan that stopped part way is resumed', async () => {
    fetch.mockReset();
    fetch
      .mockResolvedValueOnce(answer({ id: 7 }))
      .mockResolvedValueOnce(answer({ id: 7, state: 'running', steps: [{ job: 'j1' }, { waiting: true }] }));
    const plan = run({
      total: 120,
      steps: [
        { name: 'a', credits: 60 },
        { name: 'b', credits: 60 },
      ],
    });
    await approvePlan(5, 'tab1', plan);
    expect(fetch.mock.calls.map((c) => [String(c[0]), (c[1] as { method?: string })?.method])).toEqual([
      ['/api/agent/plans', 'POST'],
      ['/api/agent/plans/7/approve', 'POST'],
    ]);
    expect(JSON.parse(String((fetch.mock.calls[0][1] as { body: string }).body))).toMatchObject({
      tab: 'tab1',
      project_id: 5,
    });
    expect(plan.plan).toBe(7);
    expect(plan.state).toBe('approved');
    expect(plan.planState).toBe('running');
    expect(plan.steps.map((s) => s.job)).toEqual(['j1', undefined]);

    fetch.mockReset();
    fetch.mockResolvedValueOnce(answer({ id: 7, state: 'running', steps: [{ job: 'j1' }, { job: 'j2' }] }));
    plan.steps[1].error = 'refused';
    await approvePlan(5, 'tab1', plan);
    expect(String(fetch.mock.calls[0][0])).toBe('/api/agent/plans/7/resume');
    expect(plan.steps[1]).toMatchObject({ job: 'j2', error: null });
  });

  it('applies what the live connection says, and says whether anything changed', () => {
    const plan = run({ state: 'approved', plan: 3, planState: 'running', steps: [{ name: 'a' }, { name: 'b' }] });
    expect(applyPlan(plan, { id: 4, state: 'done', steps: [] })).toBe(false); // another plan
    expect(applyPlan(plan, { id: 3, state: 'running', steps: [{ job: 'j1' }, { waiting: true }] })).toBe(true);
    expect(applyPlan(plan, { id: 3, state: 'running', steps: [{ job: 'j1' }, { waiting: true }] })).toBe(false);
    expect(running(plan)).toBe(true);
    expect(applyPlan(plan, { id: 3, state: 'failed', steps: [{ job: 'j1' }, { error: 'No credits.' }] })).toBe(true);
    expect(plan.steps[1].error).toBe('No credits.');
    expect(running(plan)).toBe(false);
  });
});
