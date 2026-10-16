// One element helper for the shell and its widgets; no framework (ADR 0054).
export const h = <K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<Omit<HTMLElementTagNameMap[K], "style">> & { text?: string; attrs?: Record<string, string>; style?: Partial<CSSStyleDeclaration> } = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] => {
  const el = document.createElement(tag);
  const { text, attrs, style, ...rest } = props;
  Object.assign(el, rest);
  if (attrs) for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (style) Object.assign(el.style, style);
  if (text !== undefined) el.textContent = text;
  el.append(...children);
  return el;
};
