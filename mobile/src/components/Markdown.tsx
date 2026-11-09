import { Fragment, type ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts, lines, radius, spacing } from '@/theme';

/** Bold and `code` inside a line. */
function inline(text: string, key: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <Text key={`${key}-${i}`} style={styles.bold}>{part.slice(2, -2)}</Text>;
    if (part.startsWith('`') && part.endsWith('`')) return <Text key={`${key}-${i}`} style={styles.code}>{part.slice(1, -1)}</Text>;
    return <Fragment key={`${key}-${i}`}>{part}</Fragment>;
  });
}

/** Enough Markdown for a skill's recipe: headings, paragraphs, lists, quotes, code blocks and tables (as plain rows). */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r/g, '').split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    if (line.startsWith('```')) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++]);
      i += 1;
      blocks.push(
        <View key={key} style={styles.codeBlock}>
          <Text style={styles.codeText} selectable>
            {code.join('\n')}
          </Text>
        </View>,
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      blocks.push(
        <Text key={key} style={level === 1 ? styles.h1 : level === 2 ? styles.h2 : styles.h3}>
          {inline(heading[2], key)}
        </Text>,
      );
      i += 1;
      continue;
    }
    const bullet = /^(\s*)([-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      const indent = Math.min(2, Math.floor(bullet[1].length / 2));
      const marker = /\d/.test(bullet[2]) ? bullet[2].replace(')', '.') : '•';
      blocks.push(
        <View key={key} style={[styles.item, { marginLeft: indent * spacing.lg }]}>
          <Text style={styles.marker}>{marker}</Text>
          <Text style={styles.body}>{inline(bullet[3], key)}</Text>
        </View>,
      );
      i += 1;
      continue;
    }
    if (line.startsWith('>')) {
      blocks.push(
        <View key={key} style={styles.quote}>
          <Text style={styles.body}>{inline(line.replace(/^>\s?/, ''), key)}</Text>
        </View>,
      );
      i += 1;
      continue;
    }
    if (line.trim().startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      blocks.push(
        <View key={key} style={styles.table}>
          {rows
            .filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r))
            .map((r, n) => (
              <Text key={n} style={[styles.tableRow, n === 0 && styles.bold]}>
                {r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()).join('   ·   ')}
              </Text>
            ))}
        </View>,
      );
      continue;
    }
    if (!line.trim() || /^-{3,}$/.test(line.trim())) {
      i += 1;
      continue;
    }
    // A paragraph: this line and the ones after it up to a blank line or another block.
    const para: string[] = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>|\s*([-*•]|\d+[.)])\s|\s*\|)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(
      <Text key={key} style={styles.body}>
        {inline(para.join(' '), key)}
      </Text>,
    );
  }
  return <View style={styles.doc}>{blocks}</View>;
}

const styles = StyleSheet.create({
  doc: { gap: spacing.md },
  h1: { ...fonts.title2, color: colors.text, marginTop: spacing.md },
  h2: { ...fonts.title3, color: colors.text, marginTop: spacing.md },
  h3: { ...fonts.headline, color: colors.text, marginTop: spacing.sm },
  body: { ...fonts.callout, color: colors.textSecondary, flex: 1, lineHeight: lines(23) },
  bold: { fontFamily: fonts.calloutStrong.fontFamily, color: colors.text },
  code: { fontFamily: 'monospace', fontSize: 14, color: colors.accent },
  item: { flexDirection: 'row', gap: spacing.sm, paddingRight: spacing.sm },
  marker: { ...fonts.callout, color: colors.accent, minWidth: 16, lineHeight: lines(23) },
  quote: { borderLeftWidth: 3, borderLeftColor: colors.accent, paddingLeft: spacing.md },
  codeBlock: { backgroundColor: colors.surfaceRaised, borderRadius: radius.sm, padding: spacing.md },
  codeText: { fontFamily: 'monospace', fontSize: 13, lineHeight: lines(19), color: colors.text },
  table: { backgroundColor: colors.surface, borderRadius: radius.sm, padding: spacing.md, gap: 6 },
  tableRow: { ...fonts.footnote, color: colors.textSecondary },
});
