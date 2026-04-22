# Gotchas

Operational hazards that have already bitten us. Check this file before debugging a QIRA issue — odds are it's already listed.

## 1. Hard resets from onnxruntime on Haswell-EP — RESOLVED by abandoning onnxruntime

> **Scope: this gotcha is hardware-specific and library-specific, not a QIRA issue.**
> Everything below describes a problem encountered only on `monster` — a dual Intel Xeon E5‑2699 v3 (Haswell-EP) workstation on a JINGSHA X99 D4 DUAL PRO board, 36C/72T across 2 NUMA nodes — when the embedding backend used `onnxruntime`. The root cause is a documented Haswell-EP 929 MCA errata triggered by onnxruntime's cross-NUMA/HT thread affinity. On any modern CPU, any Haswell-EP system with HT disabled, or any stack that does not load onnxruntime, none of this applies. QIRA itself has no quirk here; the failure path was `import chromadb` → onnxruntime → silicon errata → hard reset.
>
> **Kept on purpose.** We don't want to forget what doesn't work. If a future contributor is tempted to bring ChromaDB's default embedding back, or adopt any other library that pulls onnxruntime in transitively (sentence-transformers under some configs, faster-whisper, rembg, etc.), this page is the record of why that path burned hours of debugging.

**Symptom (historical):** Early eu-ai-act builds hard-reset the workstation (`monster`: dual Xeon E5-2699 v3, Haswell-EP) mid-build. Instant power-cycle, no kernel panic, no dmesg trace, nothing in `journalctl`.

**Root cause (two stacked issues):**
1. **onnxruntime thread affinity.** `onnxruntime` aggressively calls `pthread_setaffinity_np` across NUMA nodes and HT siblings at session init. ChromaDB's **default** embedding function loads onnxruntime at import time, so `import chromadb` alone was enough to trigger it. Confirmed by multiple upstream issues (microsoft/onnxruntime#8313, #10104; SYSTRAN/faster-whisper#1169; rembg#448).
2. **Haswell-EP "929 Fatal MCA" errata.** E5-26xx v3 parts have a documented "Core 0 generic L2 cache — poisoned data" errata that fires under concurrent load **when hyperthreading is enabled**. Fatal MCA = immediate machine check abort = hard reset with zero kernel forensics. Matches the observed symptom exactly.

The chain: `import chromadb` → onnxruntime init → cross-NUMA affinity with HT siblings → 929 MCA → hard reset.

**Debugging history (so we don't repeat it):** Many theories were tried and ruled out before the root cause was found — PSU sag (prime suspect for a while, wrong), memory, thermals, power budget, `--parallel` tuning, `--skip-questions` isolation. `ORT_DISABLE_CPU_AFFINITY=1` was also tried and proved insufficient under the full concurrent workload (embedding + 10 keprompt subprocesses + LLM network I/O) — four mitigation-test runs on 2026-04-14 all hard-reset. Do not re-open any of those lines of inquiry.

**Resolution — two steps:**

1. **(2026-04-21) HT disabled in BIOS** as an interim MCA mitigation. `lscpu` reported `Threads per core: 1`, 36 online CPUs across 2 sockets. Builds stopped hard-resetting, but onnxruntime was still in the stack as an unexplained fragile dependency.
2. **Pivot to Model2Vec + FAISS** — the project then abandoned onnxruntime entirely. Current backend is Model2Vec (`potion-base-8M`) for embeddings + FAISS `IndexFlatL2` for the vector index. No onnxruntime, no ChromaDB, no PyTorch. The MCA trigger path is removed at the source, not just masked.

**Rules going forward:**
- **Do not reintroduce onnxruntime on `monster`**, directly or transitively. This rules out ChromaDB's default embedding function, and any library that bundles onnxruntime under the hood. If you add a new embedding or speech/vision library, verify its dependency tree.
- HT state on `monster` is no longer load-bearing for QIRA — the MCA only fires under onnxruntime's affinity pattern, and onnxruntime is no longer in the stack.
- **Safety net (keep it):** `crash_log_open()` in the builder writes fsync'd lines to `.build/crash.log`. Cheap, useful for any crash debugging, worth keeping regardless of backend.

## 2. SQLite is the source of truth; the vector index is derived state

The on-disk `{corpus}.faiss` file is never trusted as authoritative. Every build reconstructs the in-memory FAISS index from the SQLite `questions` table via `rebuild_faiss_from_db()` in `build_corpus.py`, and writes it to disk only at the end of a successful run. Unclean shutdown → stale `.faiss` file → next run rebuilds cleanly anyway. `setup_output(..., fresh=True)` additionally deletes the `.faiss` file, but the rebuild pattern means it's not load-bearing.

**Do not optimize this away.** The "always rebuild from SQLite" rule is what makes resume mode safe. A clever optimization that reads the existing FAISS file directly would reintroduce a class of corruption bugs we don't currently have.

## 3. Questions must be recoverable from SQLite (FAISS is derived state)

Two mechanisms enforce this in `build_corpus.py`:

1. Every question that goes into FAISS also goes into the SQLite `questions` table (`idx`, `section_id`, `question`). FAISS row `idx` = `questions.idx`. That is the canonical mapping used by `runtime/qira`'s `qira_search`.
2. Safety net for pre-Model2Vec corpora: `_backfill_questions_from_search_entry()` can repopulate the `questions` table from each section's `search_entry` column when `questions` is empty but `sections` is full. The extraction regex is `^- \*(.+)\*$` per line.

If you add decoration around the question bullets in `search_entry` (e.g. change `- *How do I X?*` to something else), update the regex or lose backfill.

## 4. Cross-reference "double annotation" guard

`_rewrite_text` in `examples/eu-ai-act/build_corpus.py` checks for ` (see ` immediately following a match before rewriting, to prevent `Article 6 (see eu-ai-act:4.1.1) (see eu-ai-act:4.1.1)`. Same guard is needed in any new builder that runs multiple xref passes.

## 5. Silent skip on FAISS→SQLite mismatch in `qira_search`

`runtime/qira`'s `qira_search()` has two silent-skip paths that hide build-time corruption:

1. **FAISS row with no `questions` row.** After `index.search()`, the code does `SELECT section_id FROM questions WHERE idx = ?` and falls through with `if row is None: continue`.
2. **section_id with no `sections` row.** The second lookup `SELECT title, search_entry FROM sections WHERE id = ?` has the same `continue`.

A build that wrote vectors to FAISS but partially failed to write SQLite rows will return fewer search hits than expected with no error. If search results look thin, check:

```bash
sqlite3 {corpus}.db "SELECT count(*) FROM sections"
sqlite3 {corpus}.db "SELECT count(*) FROM questions"
```

vs the FAISS vector count. Re-opening the index with `faiss.read_index` and inspecting `index.ntotal` will show how many vectors are stored.

## 6. `keprompt` must be on PATH and `prompts/` dir must exist

`call_keprompt` in `examples/eu-ai-act/build_corpus.py` runs `subprocess.run(["keprompt", "chat", "new", ...])` with `cwd=keprompt_dir`. That directory must contain a `prompts/` subdir with the `.prompt` file. The builder's `main()` auto-detects this by looking for `./prompts/` relative to the script first, then to `cwd`. If neither exists, it aborts.

Per memory `feedback_keprompt_usage.md`: use prompt **names** not paths; run from the project dir.

## 7. `qira --initialize` only picks one worked example

`runtime/qira`'s `initialize()` iterates corpora and uses the **first** corpus's `## Example` section as `$worked_example`. If you want a different corpus to drive the example shown to the LLM, either reorder (alphabetical by directory name — see `list_corpora`) or change `initialize()`.

## 8. Section IDs: always full corpus-prefixed form

Easy to slip up when writing a new builder and emit `3.2.4` instead of `eu-ai-act:3.2.4` somewhere. The full prefixed form must appear in: `sections.id`, `metadata.section_id`, all markdown content, the `## Subsections` list in `read_entry`, rewritten xrefs. Grep for raw numeric IDs after a build as a sanity check.

## 9. Don't forget `corpus.md`

The builder must write `corpus.md` with all four `## ` headings (`Name`, `Description`, `Embedding`, `Example`). Without it, `qira --initialize` skips the corpus with a warning and it won't appear in the catalog.
