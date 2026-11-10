// Joins class names, leaving out the ones that are off: cx(s.frame, selected && s.selected).
export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ');

// The classes of base.css: every screen shares them, so they stay plain names.
const SHARED = new Set(
  'btn small quiet primary danger block generate icon-btn icon muted error ok hidden row field label hint seg check notice cost search grow note danger-solid'.split(
    ' ',
  ),
);

/** For a component whose classes live in CSS Modules: css('card on') gives each name as those modules know it. A name
 *  written in several modules (a chunk of one big stylesheet, or a state several parts react to) gets all of them, and
 *  a name of base.css stays as it is too. */
export function classesOf(...modules: Readonly<Record<string, string>>[]) {
  const known = new Map<string, string>();
  const name = (token: string) => {
    let found = known.get(token);
    if (found === undefined) {
      const local = modules.flatMap((m) => m[token] ?? []);
      found = (!local.length || SHARED.has(token) ? [token, ...local] : local).join(' ');
      known.set(token, found);
    }
    return found;
  };
  return (names: string | false | null | undefined) =>
    names ? names.split(/\s+/).filter(Boolean).map(name).join(' ') : '';
}

/** One big stylesheet written as several modules: their class names together. */
export function mergeModules(...modules: Readonly<Record<string, string>>[]) {
  const all: Record<string, string> = {};
  for (const m of modules)
    for (const [name, hashed] of Object.entries(m)) all[name] = all[name] ? all[name] + ' ' + hashed : hashed;
  return all;
}
