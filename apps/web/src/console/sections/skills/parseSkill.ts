// A skill file as text: "key: value" lines, a line of three dashes, then the steps. Skills written for other tools come
// with a YAML header between two lines of dashes, sometimes two of them in a row: every header is read, the first value
// of a key wins (name, label, description and user_description stand in for id, title and desc). A plain Markdown file
// with no header works too: its name is the id, its first "# heading" the title, and all of it the steps.

export type Skill = { id: string; title: string; desc: string; version: string; words: string; text: string };

export function parseSkill(source: string, filename: string): Skill {
  let text = String(source)
    .replace(/\r\n/g, '\n')
    .replace(/^\uFEFF/, '');
  const meta: Record<string, string> = {};
  const pairs = (block: string) => {
    for (const line of block.split('\n')) {
      const at = line.indexOf(':');
      const key = line.slice(0, at).trim().toLowerCase();
      if (at <= 0 || /\s/.test(key) || key in meta) continue;
      let value = line.slice(at + 1).trim();
      if (value.length > 1 && value[0] === value[value.length - 1] && '\'"'.includes(value[0]))
        value = value.slice(1, -1);
      meta[key] = value;
    }
  };
  const header = (block: string) => block.split('\n').every((l) => !l.trim() || l.includes(':'));
  if (text.startsWith('---\n')) text = text.slice(4);
  const cut = text.indexOf('\n---\n');
  if (cut >= 0 && header(text.slice(0, cut))) {
    pairs(text.slice(0, cut));
    text = text.slice(cut + 5);
  }
  for (;;) {
    // more headers straight after the first, or a lone separator
    text = text.replace(/^\n+/, '');
    if (!text.startsWith('---\n')) break;
    const body = text.slice(4);
    const end = body.indexOf('\n---\n');
    if (end >= 0 && body.slice(0, end).trim() && header(body.slice(0, end))) {
      pairs(body.slice(0, end));
      text = body.slice(end + 5);
    } else text = body;
  }
  text = text.trim();
  const stem = (meta.id || meta.name || filename.replace(/\.(md|markdown|txt)$/i, ''))
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  const heading = (text.match(/^#\s+(.+)$/m) || [])[1];
  const about = meta.desc || meta.user_description || meta.description || '';
  // a skill that says when it applies, in quotes ('when the user says "pocket motion v2"'), is triggered by those words
  const quoted = [...(meta.description || '').matchAll(/["“]([^"”]{4,60})["”]/g)]
    .map((m) => m[1].trim().replace(/[ .]+$/, ''))
    .filter(
      (p, i, all) => p.split(/\s+/).length >= 2 && all.findIndex((q) => q.toLowerCase() === p.toLowerCase()) === i,
    );
  const words =
    meta.words && meta.words !== '(?!)'
      ? meta.words
      : quoted.length
        ? '\\b(' +
          quoted
            .map((p) =>
              p
                .split(/\s+/)
                .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
                .join('\\s+'),
            )
            .join('|') +
          ')\\b'
        : '';
  return {
    id: stem,
    title: meta.title || meta.label || heading || stem,
    desc: about.length > 160 ? about.slice(0, 160).replace(/\s+\S*$/, '') + '…' : about,
    version: meta.version || '1',
    words,
    text,
  };
}
