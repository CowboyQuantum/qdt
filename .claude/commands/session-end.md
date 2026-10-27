Close the session.

1. Run `/session-check`. Do not proceed on red.
2. File a GitHub issue for everything the session found and did not fix: bugs, gaps, bench ideas,
   pending decisions (ADR 0071; labels `found-by-agent` + `blocker`|`roadmap`|`backlog`, a milestone for
   `roadmap`; no serials, addresses or site names: the repo is public). Comment on issues the session
   touched; a fix's commit says `Fixes #N`.
3. Rewrite `docs/STATUS.md` in full using its existing headings. Keep it under one screen. State: step, done this session, in flight (with exact file paths), the open blockers by issue number, and the single next action. No backlog lists: link issues. Never append; replace.
4. For each decision made this session, write an ADR via `/adr` and link it from STATUS.md.
5. Commit everything with conventional-commit messages. Report the commit hashes.
6. Push the branch, open the pull request, and arm its watcher in the same turn (root `CLAUDE.md`,
   End step 6): subscribe to the pull request's activity and schedule the safety-net check-in. Say in
   the reply that it is armed, or which pull request is unwatched and why.
7. Summarize in three lines what a human should review.
