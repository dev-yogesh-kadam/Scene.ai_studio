// How each skill looks in the list: a symbol and a colour picked from what it is about.
import type { IconName } from '@/components/Icon';
import type { Skill } from '@/types/api';

const looks: [RegExp, IconName, string][] = [
  [/direct|script|story|scene/i, 'megaphone', '#BF5AF2'],
  [/camera|coverage|angle/i, 'videocam', '#0A84FF'],
  [/continuity|recall|chain|board/i, 'link', '#30D158'],
  [/character|asset|cast|portrait|sheet/i, 'person', '#FF9F0A'],
  [/dialogue|voice|speak|lip/i, 'chatbubbles', '#FF375F'],
  [/sound|music|audio/i, 'musical-notes', '#FF9F0A'],
  [/edit|cut|trim/i, 'cut', '#64D2FF'],
  [/motion|title|graphic/i, 'text', '#5E5CE6'],
  [/ad|product|social/i, 'megaphone', '#FF453A'],
];

export function skillLook(skill: Skill): { icon: IconName; color: string } {
  const words = `${skill.id} ${skill.title}`;
  const found = looks.find(([pattern]) => pattern.test(words));
  return found ? { icon: found[1], color: found[2] } : { icon: 'sparkles', color: '#7C6BFF' };
}
