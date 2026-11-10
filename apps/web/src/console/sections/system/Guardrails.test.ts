import { describe, expect, it } from 'vitest';
import { limitProblem } from './Guardrails';

describe('a guardrail limit as typed', () => {
  it('is a whole number in its range; 0 is "no limit" only where the range starts at 0', () => {
    expect(limitProblem('0', [0, 10_000_000])).toBeNull();
    expect(limitProblem('500', [0, 10_000_000])).toBeNull();
    expect(limitProblem('3', [1, 50])).toBeNull();
    expect(limitProblem('0', [1, 50])).toBe('1 to 50');
    expect(limitProblem('51', [1, 50])).toBe('1 to 50');
    expect(limitProblem('2.5', [1, 50])).toBe('a whole number');
    expect(limitProblem('', [1, 50])).toBe('a number');
    expect(limitProblem('lots', [1, 50])).toBe('a number');
  });
});
