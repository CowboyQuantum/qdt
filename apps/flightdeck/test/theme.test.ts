// Themes are data (ADR 0054): the built-ins validate, the JSON Schema and the validator agree, a theme
// cannot inject CSS, and the manager remembers choices per storage.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BUILTIN, DEFAULT_THEME, FLAGS, initialTheme, loadCustomThemes, type Theme, ThemeManager, themeStyle, TOKEN_KEYS, validateTheme } from "../src/workspace/theme";

const schema = JSON.parse(readFileSync(new URL("../themes/theme.schema.json", import.meta.url), "utf8")) as {
  required: string[];
  properties: { tokens: { required: string[]; properties: Record<string, unknown> }; flags: { items: { enum: string[] } } };
  $defs: Record<string, { pattern: string }>;
};

const good = (): Theme => JSON.parse(JSON.stringify(BUILTIN[0])) as Theme;

describe("built-in themes", () => {
  it("are slate, paper, steel; each validates; steel wears every flag", () => {
    expect(BUILTIN.map((t) => t.name)).toEqual(["slate", "paper", "steel"]);
    for (const t of BUILTIN) expect(validateTheme(t), t.name).toEqual([]);
    expect(BUILTIN[2]!.flags).toEqual([...FLAGS]);
    expect(BUILTIN[1]!.scheme).toBe("light");
    expect(DEFAULT_THEME.name).toBe("slate");
  });

  it("the example theme in docs/ validates too", () => {
    const ember = JSON.parse(readFileSync(new URL("../../../docs/examples/flightdeck-theme-ember.json", import.meta.url), "utf8")) as unknown;
    expect(validateTheme(ember)).toEqual([]);
  });
});

describe("theme.schema.json and validateTheme agree", () => {
  it("on the thirteen tokens, the closed flag list and the value patterns", () => {
    expect(schema.properties.tokens.required).toEqual([...TOKEN_KEYS]);
    expect(Object.keys(schema.properties.tokens.properties)).toEqual([...TOKEN_KEYS]);
    expect(schema.properties.flags.items.enum).toEqual([...FLAGS]);
    expect(schema.required).toEqual(["name", "scheme", "tokens", "type", "shape", "flags"]);
    for (const [k, v] of Object.entries(schema.$defs)) {
      const re = new RegExp(v.pattern);
      const probe = { color: ["#1A2b3c", "#12345", "red"], length: ["12px", "0.5em", "12", "calc(1px)"], fontStack: ['"IBM Plex Sans", system-ui', "x; } body { color: red }"] }[k]!;
      const t = good();
      for (const sample of probe) {
        if (k === "color") t.tokens.bg = sample;
        else if (k === "length") t.type.size = sample;
        else t.type.sans = sample;
        expect(validateTheme(t).length === 0, `${k} ${sample}`).toBe(re.test(sample));
      }
    }
  });
});

describe("validateTheme", () => {
  it("rejects what could reach a stylesheet as anything but a token", () => {
    const t = good();
    t.type.sans = 'x; } body { background: url("http://evil") }';
    expect(validateTheme(t)).toEqual(["type.sans must be a font stack"]);
    const u = good();
    (u.flags as string[]).push("marquee");
    expect(validateTheme(u)[0]).toMatch(/unknown flag "marquee"/);
    const v = good();
    (v.tokens as Record<string, string>).extra = "#000000";
    expect(validateTheme(v)).toEqual(["tokens.extra is not a token"]);
    const w = good();
    w.tokens.live = "rgb(1,2,3)";
    expect(validateTheme(w)).toEqual(["tokens.live must be #rrggbb"]);
    expect(validateTheme(null)).toEqual(["not an object"]);
    expect(validateTheme({ name: "x" }).length).toBeGreaterThan(3);
    const x = good();
    x.name = "../etc";
    expect(validateTheme(x)).toEqual(["name must be a short word (letters, digits, space, dot, dash)"]);
  });
});

describe("themeStyle", () => {
  it("maps every token to a custom property and every flag to a deco class; nothing else", () => {
    const s = themeStyle(BUILTIN[2]!);
    for (const k of TOKEN_KEYS) expect(s.properties[`--${k}`]).toBe(BUILTIN[2]!.tokens[k]);
    expect(Object.keys(s.properties)).toHaveLength(TOKEN_KEYS.length + 5);
    expect(s.classes).toEqual(FLAGS.map((f) => `deco-${f}`));
    expect(s.scheme).toBe("dark");
    expect(themeStyle(BUILTIN[0]!).classes).toEqual([]);
  });
});

describe("ThemeManager", () => {
  const memory = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m } as unknown as Storage & { m: Map<string, string> };
  };

  it("starts from the remembered theme, else the system preference", () => {
    expect(initialTheme(null, BUILTIN, true).name).toBe("paper");
    expect(initialTheme(null, BUILTIN, false).name).toBe("slate");
    expect(initialTheme("steel", BUILTIN, true).name).toBe("steel");
    expect(initialTheme("gone", BUILTIN, true).name).toBe("paper");
  });

  it("selects, adds, removes and remembers; a built-in's name cannot be taken; an invalid upload is refused", () => {
    const storage = memory();
    const worn: string[] = [];
    const m = new ThemeManager(storage, (t) => worn.push(t.name), false);
    expect(m.current.name).toBe("slate");
    expect(m.select("steel")).toBe(true);
    expect(m.select("nope")).toBe(false);
    const ember = { ...good(), name: "ember", flags: ["glow"] as Theme["flags"] };
    expect(m.add(ember)).toBe(true);
    expect(m.add({ ...good(), name: "slate" })).toBe(false);
    expect(m.add({ ...good(), name: "bad", scheme: "neon" as "dark" })).toBe(false);
    expect(m.current.name).toBe("ember");
    expect(worn).toEqual(["steel", "ember"]);
    // a fresh manager over the same storage remembers both the uploads and the choice
    const again = new ThemeManager(storage, () => {}, true);
    expect(again.custom.map((t) => t.name)).toEqual(["ember"]);
    expect(again.current.name).toBe("ember");
    again.remove("ember");
    expect(again.custom).toEqual([]);
    expect(again.current.name).toBe("slate");
    again.remove("slate"); // a built-in cannot be removed
    expect(again.available).toHaveLength(3);
  });

  it("drops invalid stored themes and survives a broken storage", () => {
    const storage = memory();
    storage.setItem("flightdeck.themes.v1", JSON.stringify([good(), { name: "junk" }]));
    expect(loadCustomThemes(storage).map((t) => t.name)).toEqual(["slate"]);
    storage.setItem("flightdeck.themes.v1", "{not json");
    expect(loadCustomThemes(storage)).toEqual([]);
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
    } as unknown as Storage;
    const m = new ThemeManager(broken, () => {}, false);
    expect(m.current.name).toBe("slate");
    expect(m.select("paper")).toBe(true);
    expect(new ThemeManager(null, () => {}, true).current.name).toBe("paper");
  });
});
