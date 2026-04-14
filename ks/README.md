# ks/ — Knowledge Store for Claude

Purpose: shared understanding of QIRA, written for **Claude** as reader, not for humans.

`docs/` is for humans and explains the *why*. `ks/` is for me and states the *what* declaratively, with file:line references, so I can rebuild working context at the start of any session without re-parsing narrative prose.

## Load order

Read in this order at session start when the task touches QIRA internals:

1. **overview.md** — what's in the repo, where each thing lives
2. **contract.md** — the non-negotiable QI/RA storage contract (corpus dir, SQLite, ChromaDB, markdown formats)
3. **runtime.md** — how `runtime/qira` behaves: CLI modes, corpus discovery, embedding selection
4. **building-corpora.md** — QI pipeline condensed; pointers to example builders
5. **keprompt.md** — the LLM harness QIRA runs under; `.prompt` format, external function protocol, `chat show` observability
6. **gotchas.md** — operational hazards (onnxruntime/Haswell crash, chroma-on-resume, embedding-fn mismatch)

## Rules for writing into ks/

- State facts. No narrative, no "we decided", no "the idea is".
- Every claim that names a file, function, or line should include a `path:line` reference so I can verify.
- Prefer tables and bullets over prose paragraphs.
- When docs/ already says something correctly, point at it — don't re-explain. ks/ exists to condense and cross-link, not to replace.
- When a fact changes (crash fixed, contract evolved), update ks/ in the same turn as the code change. Stale ks/ is worse than no ks/.
- If something is truly ephemeral (in-progress state of *this* session), it goes in memory or a plan, not ks/.
