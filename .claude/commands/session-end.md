Close the session.

1. Run `/session-check`. Do not proceed on red.
2. Rewrite `docs/STATUS.md` in full using its existing headings. Keep it under one screen. State: step, done this session, in flight (with exact file paths), known broken, and the single next action. Never append; replace.
3. For each decision made this session, write an ADR via `/adr` and link it from STATUS.md.
4. Commit everything with conventional-commit messages. Report the commit hashes.
5. Summarize in three lines what a human should review.
