# 0059 — The Script widget is a placeholder that validates and never runs; Step 6b closes on it

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6b (deliverable 6; extends 0054)

## Context
The Step 6b spec lists a Script widget as its last deliverable: "a placeholder (allowed-API panel, stage
button that only validates). A real server-side sandbox is its own ADR, not this step." The prototype
sketched a text editor beside the calls a script may make. What had to be decided was how much a
placeholder does, so that it neither pretends to run anything nor becomes dead UI.

## Decision
- **The allowed API is data** (`ALLOWED_API` in `widgets/script.ts`): six calls (`sweep`, `levels`, `run`,
  `wait`, `analyze`, `device`), each with a signature and one line of doc, shown beside the editor. Every
  call names a thing the control path already has as a schema object (ADR 0032, 0036, 0053): a script
  would compose what the widgets do by hand.
- **"stage" lints, nothing more**: every `qdt.<name>(` must be on the list; a `qdt.<name>` without a
  call is flagged; brackets and quotes must balance (comments and strings ignored, multi-line calls
  allowed). The report says plainly that nothing ran and why: execution waits for a sandbox.
- **No execution path exists**, not even behind a flag: a script that runs is server-side work (a
  sandbox, a budget, an audit trail of what it did as runs and records) and gets its own ADR when a user
  needs it. The lint is deliberately small; a real parser comes with the sandbox.
- **The text persists per browser** (`flightdeck.script.v1`), like layout and themes.
- **Step 6b closes.** Its exit criteria are met (ADR 0058 lists them); this placeholder was the last
  deliverable. The open decisions that remain (layout as a schema object, the sandbox, the release
  mirror's first widgets, themes in the registry) are carried in the step file and STATUS, not left
  implicit.

## Consequences
- Easier: the finish line's "scripting" slot exists in the workspace, with its contract visible; a user
  can write and keep a script now and run it the day the sandbox lands.
- Harder: a staged script that lints clean still does nothing, and says so every time; the allow-list
  will drift from the server's API unless the sandbox ADR ties the two (it should generate the list).

## Alternatives considered
- Run scripts in the browser against `ApiClient` — rejected: a script would hold instrument-shaped power
  without the server's compile/hold/record path and without a budget; rule 8 is about what the UI may
  know, and a script runner would blur it.
- No widget until the sandbox — rejected: the step file lists the placeholder, and the editor's contract
  (what a script may call) is worth showing now.
