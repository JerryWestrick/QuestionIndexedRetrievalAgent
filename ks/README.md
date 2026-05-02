# ks/ — Knowledge Store for Claude

Purpose: shared understanding of QIRA, written for **Claude** as reader, not for humans.

`docs/` is for humans and explains the *why*. `ks/` is for me and states the *what* declaratively, with file:line references, so I can rebuild working context at the start of any session without re-parsing narrative prose.

## Load order

Two audiences, two reading paths. Pick the one that fits your task.

### A. Building a new corpus from a new source format

This is the path for a third-party corpus author and their Claude. Read in order:

1. **overview.md** — what's in the repo
2. **contract.md** — the storage contract your output must match
3. **building-corpora.md** — the 8-step QI pipeline, mapped to the two reference builders
4. **gotchas.md** — sections **2, 3, 4, 5, 6, 8, 9** are builder-relevant; §1 (onnxruntime) and §7 (`qira --initialize`) are runtime-only, skim or skip
5. Copy `examples/python-stdlib/build_corpus.py` *or* `examples/eu-ai-act/build_corpus.py` as the starting point; rewrite steps 1–2 (parse + render) for the new format, leave the shared infrastructure alone

**Skip:** `runtime.md`, `keprompt.md` — these are about how `runtime/qira` and the KePrompt harness behave at query time, not about building corpora. Open them only if a contract question forces it.

### B. Working on QIRA internals (runtime, builder shared infra, packaging)

1. **overview.md** — what's in the repo, where each thing lives
2. **contract.md** — the non-negotiable QI/RA storage contract
3. **runtime.md** — how `runtime/qira` behaves: CLI modes, corpus discovery, embedding model
4. **building-corpora.md** — QI pipeline condensed; pointers to example builders
5. **keprompt.md** — the LLM harness QIRA runs under
6. **gotchas.md** — all sections, in order

## Rules for writing into ks/

- State facts. No narrative, no "we decided", no "the idea is".
- Every claim that names a file, function, or line should include a `path:line` reference so I can verify.
- Prefer tables and bullets over prose paragraphs.
- When docs/ already says something correctly, point at it — don't re-explain. ks/ exists to condense and cross-link, not to replace.
- When a fact changes (crash fixed, contract evolved), update ks/ in the same turn as the code change. Stale ks/ is worse than no ks/.
- If something is truly ephemeral (in-progress state of *this* session), it goes in memory or a plan, not ks/.
