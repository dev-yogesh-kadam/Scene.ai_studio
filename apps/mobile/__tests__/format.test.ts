import { clipLength, creditReason, credits, fileSize, initials, timeAgo, timeLeft } from '@scene/shared/format';

describe('timeAgo', () => {
  const now = 1_800_000_000;
  it('says how long ago in short words', () => {
    expect(timeAgo(now - 10, now)).toBe('just now');
    expect(timeAgo(now - 5 * 60, now)).toBe('5 min ago');
    expect(timeAgo(now - 3 * 3600, now)).toBe('3 h ago');
    expect(timeAgo(now - 30 * 3600, now)).toBe('yesterday');
  });
  it('never says a time in the future', () => {
    expect(timeAgo(now + 100, now)).toBe('just now');
  });
});

describe('timeLeft', () => {
  it('rounds to what a person reads', () => {
    expect(timeLeft(null)).toBeNull();
    expect(timeLeft(12)).toBe('about 10 s left');
    expect(timeLeft(2)).toBe('about 5 s left');
    expect(timeLeft(180)).toBe('about 3 min left');
    expect(timeLeft(5400)).toBe('about 1.5 h left');
  });
});

describe('clipLength and fileSize', () => {
  it('formats a length as minutes and seconds', () => {
    expect(clipLength(7)).toBe('0:07');
    expect(clipLength(135.4)).toBe('2:15');
    expect(clipLength(0)).toBeNull();
  });
  it('formats sizes', () => {
    expect(fileSize(500)).toBe('1 KB');
    expect(fileSize(2.5 * 1024 * 1024)).toBe('2.5 MB');
    expect(fileSize(null)).toBeNull();
  });
});

describe('words', () => {
  it('shortens names to initials', () => {
    expect(initials('Ada Lovelace')).toBe('AL');
    expect(initials('  yogesh  ')).toBe('Y');
    expect(initials('Ada Byron King')).toBe('AB');
  });
  it('names credit changes', () => {
    expect(creditReason('welcome')).toBe('Welcome credits');
    expect(creditReason('admin grant')).toBe('From an admin');
    expect(creditReason('something new')).toBe('Something new');
    expect(credits(1500)).toBe(`${(1500).toLocaleString()} cr`);
  });
});
