Write an Architecture Decision Record for: $ARGUMENTS

1. Determine the next number: `ls docs/adr/ | sort | tail -1`.
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-<kebab-title>.md`.
3. Fill every section. "Context" states the forces, "Decision" is one or two sentences in the imperative, "Consequences" lists what becomes easier and what becomes harder, "Alternatives" names what was rejected and why.
4. If this supersedes an earlier ADR, set that ADR's status line to `Superseded by NNNN` — that line is the only edit ever permitted to a merged ADR.
5. Add the ADR to the index table in `docs/adr/README.md`.
