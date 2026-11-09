import { fireEvent, render, screen } from '@testing-library/react-native';

import { Button } from '@/components/Button';
import { Markdown } from '@/components/Markdown';
import { slotLabel } from '@/components/RefPicker';
import { skillLook } from '@/lib/skills';
import type { Skill } from '@/types/api';

describe('Markdown', () => {
  it('shows headings, lists, bold and code from a recipe', async () => {
    await render(<Markdown text={'# Directing\n\nPlan the **shots** first.\n\n- one\n- two\n\n1. first\n\nUse `/director`.'} />);
    expect(screen.getByText('Directing')).toBeTruthy();
    expect(screen.getByText('shots')).toBeTruthy();
    expect(screen.getByText('one')).toBeTruthy();
    expect(screen.getByText('1.')).toBeTruthy();
    expect(screen.getByText('/director')).toBeTruthy();
  });
  it('keeps code blocks as they are', async () => {
    await render(<Markdown text={'```\nline one\nline two\n```'} />);
    expect(screen.getByText('line one\nline two')).toBeTruthy();
  });
});

describe('Button', () => {
  it('is a button to a screen reader, and presses', async () => {
    const pressed = jest.fn();
    await render(<Button label="Generate" onPress={pressed} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Generate' }));
    expect(pressed).toHaveBeenCalledTimes(1);
  });
  it('does nothing while busy or switched off', async () => {
    const pressed = jest.fn();
    await render(<Button label="Generate" onPress={pressed} disabled />);
    await fireEvent.press(screen.getByRole('button'));
    expect(pressed).not.toHaveBeenCalled();
  });
});

describe('labels', () => {
  it('reads a reference slot plainly', () => {
    expect(slotLabel('REFERENCE 1 (character, product, outfit)')).toBe('Reference 1');
    expect(slotLabel('Start frame')).toBe('Start frame');
  });
  it('gives each skill a fitting symbol', () => {
    const skill = (id: string, title: string): Skill => ({ id, title, version: 1, desc: '', text: '', words: '', next: [], craft: true });
    expect(skillLook(skill('director', 'Directing a script')).icon).toBe('megaphone');
    expect(skillLook(skill('camera-coverage', 'Camera angles')).icon).toBe('videocam');
    expect(skillLook(skill('mystery', 'Something else')).icon).toBe('sparkles');
  });
});
