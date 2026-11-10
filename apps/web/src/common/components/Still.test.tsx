import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Still } from './Still';
import { again } from './retryOnce';

describe('a still whose poster is not ready yet', () => {
  afterEach(() => vi.useRealTimers());

  it('asks once more a second later, with a cache-buster, then gives up quietly', () => {
    vi.useFakeTimers();
    const { container } = render(<Still url="/api/library/7/file" kind="video" name="Kite" />);
    const img = () => container.querySelector('img')!;
    expect(img().getAttribute('src')).toBe('/api/library/7/poster');
    fireEvent.error(img()); // the 503
    expect(img().getAttribute('src')).toBe('/api/library/7/poster'); // not at once
    void act(() => void vi.advanceTimersByTime(1000));
    expect(img().getAttribute('src')).toBe('/api/library/7/poster?r=1');
    fireEvent.error(img());
    void act(() => void vi.advanceTimersByTime(5000));
    expect(img().getAttribute('src')).toBe('/api/library/7/poster?r=1'); // no third try
    expect(img()).toHaveAttribute('alt', 'Kite');
  });

  it('adds the cache-buster to an address that has a query already', () => {
    expect(again('/api/x/poster?w=320')).toBe('/api/x/poster?w=320&r=1');
  });
});
