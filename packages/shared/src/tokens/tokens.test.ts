// The phone site's values are what tokens.json says (the web's CSS is checked by node packages/shared/tokens/build.mjs
// --check, in CI and npm run tokens:check).
import { describe, expect, it } from 'vitest';
import tokens from '../../tokens/tokens.json';
import { dark, light, radius, spacing } from './phone';

describe('the design tokens', () => {
  it("the phone site's values are tokens.json's", () => {
    expect(dark).toEqual(tokens.phone.dark);
    expect(light).toEqual(tokens.phone.light);
    expect(spacing).toEqual(tokens.phone.spacing);
    expect(radius).toEqual(tokens.phone.radius);
    expect(Object.keys(light).sort()).toEqual(Object.keys(dark).sort());
  });
});
