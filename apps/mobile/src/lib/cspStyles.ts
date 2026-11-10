// The phone site under the studio's Content-Security-Policy, which allows no inline style (style-src 'self'): React
// Native Web, Reanimated, expo-font and expo-image write their CSS into <style> elements they make while the site runs
// and put in the page's head, and the policy blocks every one of them (the site drew unstyled).
//
// Here a <style> element made by a script never goes into the page: what it holds goes into a constructed style sheet
// that the document adopts, which is CSS set through the CSSOM, as the web studio's style objects are, and which the
// policy allows. Its `sheet` is that constructed sheet (insertRule works on it), text put in it replaces the sheet's
// rules, the head "takes" it (appendChild, insertBefore, append, prepend; removeChild and remove() let it go), the
// document finds it by its id, and the load event the libraries wait for is sent. This allows no script and no style
// from elsewhere: the rules still come only from the site's own scripts. index.ts runs it before those libraries load.

type Patched = Document & { sceneStyles?: true };

/** Installs it on this document. False where the browser has no constructed style sheets (then nothing changes). */
export function installStylesUnderPolicy(doc: Document | undefined = globalThis.document): boolean {
  if (!doc?.head || !('adoptedStyleSheets' in doc) || typeof CSSStyleSheet === 'undefined') return false;
  if ((doc as Patched).sceneStyles) return true;
  (doc as Patched).sceneStyles = true;
  const head = doc.head;

  const sheets = new WeakMap<HTMLStyleElement, CSSStyleSheet>();
  const held = new Set<HTMLStyleElement>(); // the elements the head took, in the order it took them
  const fill = (sheet: CSSStyleSheet, text: string) => {
    try {
      sheet.replaceSync(text);
    } catch {
      // CSS the browser can't read is dropped, as a <style> element would drop it
    }
  };
  const sheetOf = (element: HTMLStyleElement) => {
    let sheet = sheets.get(element);
    if (!sheet) {
      sheet = new CSSStyleSheet();
      if (element.textContent) fill(sheet, element.textContent);
      sheets.set(element, sheet);
    }
    return sheet;
  };
  // The adopted sheets: the document's own (none, unless something else adopts one) and then those of the held elements.
  const ours = new Set<CSSStyleSheet>();
  const adoptAll = () => {
    const now = [...held].map(sheetOf);
    doc.adoptedStyleSheets = [...doc.adoptedStyleSheets.filter((s) => !ours.has(s)), ...now];
    ours.clear();
    now.forEach((s) => ours.add(s));
  };
  const take = (element: HTMLStyleElement) => {
    if (held.has(element)) return;
    held.add(element);
    adoptAll();
    setTimeout(() => element.dispatchEvent(new Event('load')), 0);
  };
  const letGo = (element: HTMLStyleElement) => {
    if (held.delete(element)) adoptAll();
  };

  const made = new WeakSet<Node>();
  const ourStyle = (node: unknown): node is HTMLStyleElement => node instanceof HTMLStyleElement && made.has(node);
  const create = doc.createElement;
  doc.createElement = function (this: Document, tag: string, options?: ElementCreationOptions) {
    const element = create.call(this, tag, options);
    if (element instanceof HTMLStyleElement) {
      made.add(element);
      Object.defineProperty(element, 'sheet', { configurable: true, get: () => sheetOf(element) });
      element.remove = () => letGo(element);
      // text put in it (textContent, a text node appended) replaces the rules
      new MutationObserver(() => fill(sheetOf(element), element.textContent || '')).observe(element, {
        childList: true,
        characterData: true,
        subtree: true,
      });
    }
    return element;
  } as Document['createElement'];

  const byId = doc.getElementById;
  doc.getElementById = function (this: Document, id: string) {
    return byId.call(this, id) ?? [...held].find((e) => e.id === id) ?? null;
  };

  const appendChild = head.appendChild;
  const insertBefore = head.insertBefore;
  const removeChild = head.removeChild;
  const append = head.append;
  const prepend = head.prepend;
  head.appendChild = function <T extends Node>(this: HTMLHeadElement, node: T): T {
    if (ourStyle(node)) take(node);
    else appendChild.call(this, node);
    return node;
  };
  head.insertBefore = function <T extends Node>(this: HTMLHeadElement, node: T, child: Node | null): T {
    if (ourStyle(node)) take(node);
    else insertBefore.call(this, node, child);
    return node;
  };
  head.removeChild = function <T extends Node>(this: HTMLHeadElement, node: T): T {
    if (ourStyle(node)) letGo(node);
    else removeChild.call(this, node);
    return node;
  };
  head.append = function (this: HTMLHeadElement, ...nodes: (Node | string)[]) {
    nodes.filter(ourStyle).forEach(take);
    append.apply(
      this,
      nodes.filter((n) => !ourStyle(n)),
    );
  };
  head.prepend = function (this: HTMLHeadElement, ...nodes: (Node | string)[]) {
    nodes.filter(ourStyle).forEach(take);
    prepend.apply(
      this,
      nodes.filter((n) => !ourStyle(n)),
    );
  };
  return true;
}
