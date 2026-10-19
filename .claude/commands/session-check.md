Verify the current work is actually done before claiming it.

Run, and paste the results:
- `uv run pytest -q`
- `bash scripts/check_all.sh`
- `git status --short`

Then answer, honestly, each of:
- Does this change belong to the current step's Deliverables in its `docs/steps/` file, an accepted ADR, or a `roadmap`/`blocker` issue (ADR 0071)? If it crept, say what, and move the crept part to an issue.
- Was everything found and not fixed filed as an issue?
- Quote the step's Exit criteria. Which are now met? Which remain? (Flip its Status line only when all are met.)
- Did any decision get made that a future session could ask "why?" about? If yes, an ADR is required (`/adr`).
- Did a schema change? If yes, were all consumers, the migration, and the tests updated in the same commit?
- Did a pydantic field get added without `description=`?
- Would `docs/STATUS.md`, read cold by a fresh session, let it continue without asking you anything?
