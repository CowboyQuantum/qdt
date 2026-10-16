// Themes are data (ADR 0054): a JSON file of colour tokens, type, shape, a scheme, and a closed
// allow-list of decoration flags that switch stylesheet classes on. A theme can never inject CSS: every
// value lands in a CSS custom property or a class name from FLAGS. `themes/theme.schema.json` is the
// same contract for files; `test/theme.test.ts` keeps the two in step.
import paper from "../../themes/paper.json";
import slate from "../../themes/slate.json";
import steel from "../../themes/steel.json";

export const TOKEN_KEYS = ["bg", "panel", "panel-2", "line", "line-strong", "text", "text-2", "text-3", "live", "live-ink", "ok", "warn", "sel"] as const;
export type TokenKey = (typeof TOKEN_KEYS)[number];

/** The decoration flags a theme may switch on; each is a `deco-<flag>` class on <html> with rules in index.html. */
export const FLAGS = ["caps", "brackets", "graticule", "glow", "flat"] as const;
export type Flag = (typeof FLAGS)[number];

export interface Theme {
  name: string;
  scheme: "dark" | "light";
  tokens: Record<TokenKey, string>;
  type: { sans: string; mono: string; size: string };
  shape: { radius: string; paneRadius: string };
  flags: Flag[];
}

export const BUILTIN: readonly Theme[] = [slate as Theme, paper as Theme, steel as Theme];
export const DEFAULT_THEME = BUILTIN[0]!;

const HEX = /^#[0-9a-fA-F]{6}$/;
/** A CSS length: a number with a unit (px, em, rem, %); nothing else gets near a stylesheet. */
const LENGTH = /^\d+(\.\d+)?(px|em|rem|%)$/;
/** A font stack: names, quotes, commas, spaces and hyphens only; no url(), no braces, no semicolons. */
const FONTS = /^[\w\s"',-]+$/;
const NAME = /^[\w][\w .-]{0,39}$/;

/** Validate an untrusted object as a Theme. Returns the problems, empty when it is one. */
export function validateTheme(t: unknown): string[] {
  if (!t || typeof t !== "object") return ["not an object"];
  const o = t as Record<string, unknown>;
  const errs: string[] = [];
  if (typeof o.name !== "string" || !NAME.test(o.name)) errs.push("name must be a short word (letters, digits, space, dot, dash)");
  if (o.scheme !== "dark" && o.scheme !== "light") errs.push("scheme must be dark|light");
  const tokens = o.tokens as Record<string, unknown> | undefined;
  if (!tokens || typeof tokens !== "object") errs.push("missing tokens");
  else {
    for (const k of TOKEN_KEYS) if (!HEX.test(String(tokens[k] ?? ""))) errs.push(`tokens.${k} must be #rrggbb`);
    for (const k of Object.keys(tokens)) if (!(TOKEN_KEYS as readonly string[]).includes(k)) errs.push(`tokens.${k} is not a token`);
  }
  const type = o.type as Record<string, unknown> | undefined;
  if (!type || typeof type !== "object") errs.push("missing type");
  else {
    for (const k of ["sans", "mono"]) if (!FONTS.test(String(type[k] ?? ""))) errs.push(`type.${k} must be a font stack`);
    if (!LENGTH.test(String(type.size ?? ""))) errs.push("type.size must be a length");
  }
  const shape = o.shape as Record<string, unknown> | undefined;
  if (!shape || typeof shape !== "object") errs.push("missing shape");
  else for (const k of ["radius", "paneRadius"]) if (!LENGTH.test(String(shape[k] ?? ""))) errs.push(`shape.${k} must be a length`);
  if (!Array.isArray(o.flags)) errs.push("flags must be a list");
  else for (const f of o.flags as unknown[]) if (!(FLAGS as readonly unknown[]).includes(f)) errs.push(`unknown flag ${JSON.stringify(f)}; allowed: ${FLAGS.join(", ")}`);
  return errs;
}

/** The custom properties and class names a theme becomes; pure, so applying is testable without a DOM. */
export function themeStyle(t: Theme): { properties: Record<string, string>; classes: string[]; scheme: "dark" | "light" } {
  const properties: Record<string, string> = {};
  for (const k of TOKEN_KEYS) properties[`--${k}`] = t.tokens[k];
  properties["--sans"] = t.type.sans;
  properties["--mono"] = t.type.mono;
  properties["--fs"] = t.type.size;
  properties["--r"] = t.shape.radius;
  properties["--pane-r"] = t.shape.paneRadius;
  return { properties, classes: t.flags.map((f) => `deco-${f}`), scheme: t.scheme };
}

/** Put a theme on the document: properties on :root, deco classes on <html>, colour-scheme. */
export function applyTheme(t: Theme, root: HTMLElement = document.documentElement): void {
  const { properties, classes, scheme } = themeStyle(t);
  for (const [k, v] of Object.entries(properties)) root.style.setProperty(k, v);
  for (const c of [...root.classList]) if (c.startsWith("deco-")) root.classList.remove(c);
  root.classList.add(...classes);
  root.style.colorScheme = scheme;
  root.dataset.theme = scheme;
  root.dataset.themeName = t.name;
}

export const WEBFONTS_KEY = "flightdeck.webfonts.v1";
const WEBFONTS_HREF = "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap";

/** Load the Plex web fonts the built-in themes name, or not: a per-browser choice (ADR 0061), off by
 * default because a bench is offline and the stacks fall back to system fonts. */
export function setWebFonts(on: boolean, doc: Document = document): void {
  const had = doc.getElementById("webfonts");
  if (on && !had) {
    const link = doc.createElement("link");
    link.id = "webfonts";
    link.rel = "stylesheet";
    link.href = WEBFONTS_HREF;
    doc.head.append(link);
  } else if (!on && had) had.remove();
}

export function loadWebFonts(storage: Pick<Storage, "getItem"> | null): boolean {
  try {
    return storage?.getItem(WEBFONTS_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveWebFonts(on: boolean, storage: Pick<Storage, "setItem"> | null): void {
  try {
    storage?.setItem(WEBFONTS_KEY, on ? "1" : "0");
  } catch {
    /* no storage */
  }
}

export const THEME_KEY = "flightdeck.theme.v1";
export const CUSTOM_THEMES_KEY = "flightdeck.themes.v1";

/** Uploaded themes live per browser (Step 6b open decision: default per browser, not the registry). */
export function loadCustomThemes(storage: Pick<Storage, "getItem"> | null): Theme[] {
  try {
    const raw: unknown = JSON.parse(storage?.getItem(CUSTOM_THEMES_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((t) => validateTheme(t).length === 0).map((t) => t as Theme) : [];
  } catch {
    return [];
  }
}

export function saveCustomThemes(themes: readonly Theme[], storage: Pick<Storage, "setItem"> | null): void {
  try {
    storage?.setItem(CUSTOM_THEMES_KEY, JSON.stringify(themes));
  } catch {
    /* no storage */
  }
}

export function loadThemeName(storage: Pick<Storage, "getItem"> | null): string | null {
  try {
    return storage?.getItem(THEME_KEY) ?? null;
  } catch {
    return null;
  }
}

export function saveThemeName(name: string, storage: Pick<Storage, "setItem"> | null): void {
  try {
    storage?.setItem(THEME_KEY, name);
  } catch {
    /* no storage */
  }
}

/** Which theme to start with: the remembered one if it still exists, else the system's light/dark preference. */
export function initialTheme(remembered: string | null, available: readonly Theme[], prefersLight: boolean): Theme {
  const found = remembered ? available.find((t) => t.name === remembered) : undefined;
  if (found) return found;
  return available.find((t) => t.name === (prefersLight ? "paper" : "slate")) ?? DEFAULT_THEME;
}

/** The themes the app offers and the one it wears: built-ins plus what the user uploaded, remembered per browser. */
export class ThemeManager {
  readonly builtin: readonly Theme[] = BUILTIN;
  custom: Theme[];
  current: Theme;

  constructor(
    private readonly storage: Storage | null,
    private readonly applyTo: (t: Theme) => void,
    prefersLight: boolean,
  ) {
    this.custom = loadCustomThemes(storage);
    this.current = initialTheme(loadThemeName(storage), this.available, prefersLight);
  }

  get available(): Theme[] {
    return [...this.builtin, ...this.custom];
  }

  apply(): void {
    this.applyTo(this.current);
  }

  select(name: string): boolean {
    const t = this.available.find((x) => x.name === name);
    if (!t) return false;
    this.current = t;
    saveThemeName(name, this.storage);
    this.apply();
    return true;
  }

  /** Add (or replace by name) an uploaded theme and wear it. A built-in's name cannot be taken. */
  add(t: Theme): boolean {
    if (validateTheme(t).length || this.builtin.some((b) => b.name === t.name)) return false;
    this.custom = [...this.custom.filter((x) => x.name !== t.name), t];
    saveCustomThemes(this.custom, this.storage);
    return this.select(t.name);
  }

  remove(name: string): void {
    if (!this.custom.some((x) => x.name === name)) return;
    this.custom = this.custom.filter((x) => x.name !== name);
    saveCustomThemes(this.custom, this.storage);
    if (this.current.name === name) this.select(DEFAULT_THEME.name);
  }
}
