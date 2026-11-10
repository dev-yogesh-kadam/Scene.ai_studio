import app from '../app.json';
import { releases } from '@/lib/whatsNew';

describe('a release', () => {
  it("has a What's New entry for the version in app.json", () => {
    expect(releases[0].version).toBe(app.expo.version);
    expect(releases[0].points.length).toBeGreaterThan(0);
  });
  it('lists versions newest first', () => {
    const numbers = releases.map((r) => r.version.split('.').map(Number));
    for (let i = 1; i < numbers.length; i += 1) {
      const [a, b] = [numbers[i - 1], numbers[i]];
      expect(a[0] * 1e6 + a[1] * 1e3 + a[2]).toBeGreaterThan(b[0] * 1e6 + b[1] * 1e3 + b[2]);
    }
  });
  it('is built as a website the studio serves at /m', () => {
    expect(app.expo.platforms).toEqual(['web']);
    expect(app.expo.web.output).toBe('single');
    expect(app.expo.experiments.baseUrl).toBe('/m');
  });
});
