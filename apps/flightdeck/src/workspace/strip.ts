// The top strip (ADR 0054): stand, device, source, the live pill, what the next Run does, the one Run
// button, stream telemetry and progress, messages, the replay picker and the theme menu. It holds no
// instrument or registry handle (rule 8): the stand and device come from the API as records.
import type { ApiClient } from "../api/client";
import type { Run } from "../schema/api";
import type { Datasets } from "../stream/datasets";
import type { Bus } from "./bus";
import { h } from "./dom";
import { FLAGS, loadWebFonts, saveWebFonts, setWebFonts, type ThemeManager, validateTheme, type Theme } from "./theme";
import { safeStorage } from "./layout";

export interface StripOptions {
  bus: Bus;
  api: ApiClient;
  datasets: Datasets;
  themes: ThemeManager;
  onReplayFile(file: File): void;
  /** Against a read server (ADR 0074): no stand to name and nothing to run, so the Run cluster is absent. */
  readOnly?: boolean;
}

export function mountStrip(header: HTMLElement, o: StripOptions): void {
  const stand = h("b", { id: "stand", text: "—" });
  const device = h("b", { id: "device", text: "—" });
  const source = h("b", { id: "source", text: "—" });
  const liveText = h("span", { id: "live-text", text: "idle" });
  const pill = h("span", { id: "live-pill", className: "pill" }, h("span", { className: "dot" }), liveText);
  const nextRun = h("span", { id: "next-run", className: "kv" });
  const plan = h("span", { id: "plan", className: "kv", title: "The last compiled plan; stale when an editor changed since" });
  const run = h("button", { id: "run", className: "primary", type: "button", text: "Run", title: "Compile what the editors hold (if they changed) and run it" });
  const runState = h("span", { id: "run-state", className: "kv" });
  const abort = h("button", { id: "abort", type: "button", text: "abort", hidden: true });
  const status = h("span", { id: "status", className: "kv", text: "connecting…" });
  const progressBar = h("i");
  const progress = h("span", { id: "progress", className: "progress strip-progress", attrs: { role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "1" } }, progressBar);
  const message = h("span", { id: "message" });
  const file = h("input", { id: "file", type: "file", accept: ".qdtrec" });
  const themeButton = h("button", { id: "theme", type: "button", text: `Theme: ${o.themes.current.name}`, attrs: { "aria-haspopup": "menu", "aria-expanded": "false" } });
  const command = o.readOnly ? [] : [nextRun, plan, run, runState, abort];
  header.replaceChildren(
    h("h1", { text: "Flight Deck" }),
    h("span", { className: "kv" }, "stand ", stand),
    h("span", { className: "kv" }, "device ", device),
    h("span", { className: "kv" }, "source ", source),
    pill,
    ...command,
    h("span", { className: "spacer" }),
    status,
    progress,
    message,
    h("label", { className: "kv" }, "replay ", file),
    themeButton,
  );

  if (o.readOnly) stand.textContent = "registry"; // a read server drives no stand; it serves the records
  else
    o.api
      .stand()
      .then((s) => {
        stand.textContent = s.stand_id;
        o.bus.emit("stand", { stand: s });
      })
      .catch(() => (stand.textContent = "?"));
  o.api
    .devices()
    .then((d) => (device.textContent = d[0]?.device_id ?? "—"))
    .catch(() => (device.textContent = "?"));
  source.textContent = o.datasets.label || "—";
  o.datasets.onSource((label) => (source.textContent = label));

  run.addEventListener("click", () => o.bus.emit("run:request", {}));
  abort.addEventListener("click", () => o.bus.emit("run:abort", {}));
  o.bus.on("run:next", ({ summary }) => (nextRun.textContent = summary ? `next: ${summary}` : ""));
  let planId = "";
  o.bus.on("plan:compiled", ({ planId: id }) => {
    planId = id;
    plan.replaceChildren("plan ", h("b", { text: id.slice(0, 8) }));
    plan.classList.remove("stale");
  });
  o.bus.on("plan:changed", () => {
    if (!planId) return;
    plan.replaceChildren("plan ", h("b", { text: planId.slice(0, 8) }), h("span", { className: "stale-mark", text: " · stale" }));
    plan.classList.add("stale");
  });
  // the runs the UI started, by id: the strip shows the one executing (or the latest), and how many wait
  const runs = new Map<string, Run>();
  const TERMINAL = new Set(["completed", "aborted", "failed"]);
  o.bus.on("run:state", ({ run: r }) => {
    if (!r) return;
    runs.set(r.run_id, r);
    const live = [...runs.values()].filter((x) => !TERMINAL.has(x.state));
    const shown = live.find((x) => x.state === "running") ?? live[0] ?? r;
    const queued = live.filter((x) => x.state === "queued").length - (shown.state === "queued" ? 1 : 0);
    runState.replaceChildren(
      "run ",
      h("b", { text: shown.run_id.slice(0, 8) }),
      ` ${shown.definition_name} · ${shown.state}${shown.record_id ? ` → record ${shown.record_id.slice(0, 8)}` : ""}${queued > 0 ? ` · ${queued} queued` : ""}`,
    );
    abort.hidden = live.length === 0;
  });
  o.bus.on("stream:state", ({ state, progress: p, summary }) => {
    pill.classList.toggle("live", state === "live");
    liveText.textContent = state;
    if (summary) status.textContent = summary;
    progressBar.style.width = p === null ? "0" : `${(100 * p).toFixed(1)}%`;
    progress.setAttribute("aria-valuenow", p === null ? "0" : p.toFixed(3));
  });
  o.bus.on("say", ({ text, error }) => {
    message.textContent = text;
    message.className = error ? "error" : "";
  });
  file.addEventListener("change", () => {
    const f = file.files?.[0];
    if (f) o.onReplayFile(f);
  });
  themeButton.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleThemeMenu(themeButton, o.themes, (t) => (themeButton.textContent = `Theme: ${t.name}`));
  });
}

/** The theme menu: built-ins, uploaded themes (removable), load a file, export the current one. */
function toggleThemeMenu(button: HTMLButtonElement, themes: ThemeManager, onPick: (t: Theme) => void): void {
  const open = document.querySelector<HTMLElement>(".menu.theme");
  if (open) {
    open.remove();
    button.setAttribute("aria-expanded", "false");
    return;
  }
  const menu = h("div", { className: "menu theme", attrs: { role: "menu" } });
  const error = h("div", { className: "error", attrs: { "data-error": "" } });
  const rebuild = () => {
    menu.replaceChildren();
    const item = (t: Theme, removable: boolean) => {
      const b = h("button", { type: "button", className: "item", text: `${t.name}${themes.current.name === t.name ? " ✓" : ""}`, attrs: { role: "menuitem", "data-theme": t.name } });
      b.addEventListener("click", () => {
        themes.select(t.name);
        onPick(themes.current);
        closeMenu();
      });
      if (!removable) return b;
      const rm = h("button", { type: "button", className: "icon", text: "✕", title: "Remove", attrs: { "aria-label": `Remove theme ${t.name}` } });
      rm.addEventListener("click", (e) => {
        e.stopPropagation();
        themes.remove(t.name);
        onPick(themes.current);
        rebuild();
      });
      return h("div", { className: "row" }, b, rm);
    };
    menu.append(h("div", { className: "row hint", text: "built in" }), ...themes.builtin.map((t) => item(t, false)));
    if (themes.custom.length) menu.append(h("div", { className: "row hint", text: "uploaded" }), ...themes.custom.map((t) => item(t, true)));
    const load = h("button", { type: "button", text: "Load theme file…" });
    load.addEventListener("click", () => {
      const input = h("input", { type: "file", accept: "application/json,.json" });
      input.addEventListener("change", async () => {
        const f = input.files?.[0];
        if (!f) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(await f.text());
        } catch {
          error.textContent = "not valid JSON";
          return;
        }
        if (parsed && typeof parsed === "object" && !("name" in parsed)) (parsed as { name?: string }).name = f.name.replace(/\.json$/, "");
        const errs = validateTheme(parsed);
        if (errs.length) {
          error.textContent = errs.join("; ");
          return;
        }
        themes.add(parsed as Theme);
        onPick(themes.current);
        closeMenu();
      });
      input.click();
    });
    const fonts = h("input", { type: "checkbox", name: "webfonts", checked: loadWebFonts(safeStorage()) });
    fonts.addEventListener("change", () => {
      saveWebFonts(fonts.checked, safeStorage());
      setWebFonts(fonts.checked);
    });
    const exportButton = h("button", { type: "button", text: "Export current" });
    exportButton.addEventListener("click", () => {
      const t = themes.current;
      const blob = new Blob([JSON.stringify(t, null, 2)], { type: "application/json" });
      const a = h("a", { href: URL.createObjectURL(blob), download: `flightdeck-theme-${t.name}.json` });
      a.click();
      URL.revokeObjectURL(a.href);
    });
    menu.append(
      h("div", { className: "row" }, load, exportButton),
      h("label", { className: "row hint" }, h("span", { text: "load the Plex web fonts (online only; off at the bench)" }), fonts),
      h("div", { className: "row hint", text: `JSON: name, scheme, tokens (13 colours), type, shape, flags [${FLAGS.join(", ")}]` }),
      error,
    );
  };
  const onDocClick = () => closeMenu();
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      closeMenu();
      button.focus();
    }
  };
  const closeMenu = () => {
    menu.remove();
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKey);
  };
  rebuild();
  menu.addEventListener("click", (e) => e.stopPropagation());
  document.body.append(menu);
  button.setAttribute("aria-expanded", "true");
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  // registered now, not on a timer: the opening click never reaches the document (the button stops it),
  // and a key pressed right after the click must already close the menu
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
}
