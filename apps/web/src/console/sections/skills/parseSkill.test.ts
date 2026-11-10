import { describe, expect, it } from 'vitest';
import { parseSkill } from './parseSkill';

describe('parseSkill', () => {
  it('reads "key: value" lines, then the steps', () => {
    const skill = parseSkill(
      'id: Short Film\ntitle: A film\nwords: \\bfilm\\b\nversion: 3\n---\n# Steps\nDo it',
      'x.md',
    );
    expect(skill).toEqual({
      id: 'short-film',
      title: 'A film',
      desc: '',
      version: '3',
      words: '\\bfilm\\b',
      text: '# Steps\nDo it',
    });
  });

  it('reads two headers in a row, the first value of a key winning', () => {
    const skill = parseSkill(
      '---\nname: first\nlabel: "One"\n---\n\n---\nname: second\ndescription: About it\n---\nSteps',
      'x.md',
    );
    expect(skill.id).toBe('first');
    expect(skill.title).toBe('One');
    expect(skill.desc).toBe('About it');
    expect(skill.text).toBe('Steps');
  });

  it('takes a plain Markdown file: its name, its first heading, all of it', () => {
    const skill = parseSkill('# My recipe\r\nFirst step', 'My Recipe.md');
    expect(skill.id).toBe('my-recipe');
    expect(skill.title).toBe('My recipe');
    expect(skill.text).toBe('# My recipe\nFirst step');
  });

  it('turns the quoted phrases of a description into trigger words', () => {
    const skill = parseSkill(
      '---\nname: pm\ndescription: Use when the user says "pocket motion v2" or "one"\n---\nSteps',
      'x.md',
    );
    expect(skill.words).toBe('\\b(pocket\\s+motion\\s+v2)\\b');
  });
});
