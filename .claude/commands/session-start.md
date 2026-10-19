Begin a qdt work session.

1. Read `CLAUDE.md`, then `docs/STATUS.md`, then the `docs/steps/` file STATUS.md names as the current step.
2. Read the nested `CLAUDE.md` of each package named in STATUS.md's "next action".
3. Run `git status` and `git log --oneline -10`. If the tree is dirty or the branch is not `main`/`step-*`, stop and report.
4. List the open issues that bound the session: `gh issue list --label blocker` and
   `gh issue list --label roadmap --milestone "<current milestone>"` (ADR 0071). Name any blocker.
5. Restate the next action from STATUS.md in one sentence. If the user's request differs, say so explicitly and ask which to follow before writing code.
6. Create or check out the branch `step-N/<short-name>`.
Do not read anything else yet.
