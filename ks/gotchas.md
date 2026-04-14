# Gotchas

Operational hazards that have already bitten us. Check this file before debugging a QIRA issue — odds are it's already listed.

## 1. Hard resets from onnxruntime on Haswell-EP — RESOLVED, do not regress

**Symptom (historical):** Early eu-ai-act builds hard-reset the workstation (`monster`: dual Xeon E5-2699 v3, Haswell-EP) mid-build. Instant power-cycle, no kernel panic, no dmesg trace, nothing in `journalctl`.

**Root cause (two stacked issues):**
1. **onnxruntime thread affinity.** `onnxruntime` aggressively calls `pthread_setaffinity_np` across NUMA nodes and HT siblings at session init. ChromaDB's **default** embedding function loads onnxruntime at import time, so `import chromadb` alone was enough to trigger it. Confirmed by multiple upstream issues (microsoft/onnxruntime#8313, #10104; SYSTRAN/faster-whisper#1169; rembg#448).
2. **Haswell-EP "929 Fatal MCA" errata.** E5-26xx v3 parts have a documented "Core 0 generic L2 cache — poisoned data" errata that fires under concurrent load **when hyperthreading is enabled**. Fatal MCA = immediate machine check abort = hard reset with zero kernel forensics. Matches the observed symptom exactly.

The chain: `import chromadb` → onnxruntime init → cross-NUMA affinity with HT siblings → 929 MCA → hard reset.

**Debugging history (so we don't repeat it):** Many theories were tried and ruled out before the root cause was found — **PSU sag** (prime suspect for a while, wrong), memory, thermals, power budget, `--parallel` tuning, `--skip-questions` isolation. Do not re-open any of those lines of inquiry. The fix is below.

**Resolution:** Switched eu-ai-act builder to `SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")` (PyTorch) — see `examples/eu-ai-act/build_corpus.py:985`. Crashes stopped immediately.

**Rules for new builders on this workstation:**
- **Never use ChromaDB's default embedding function.** Always pass `SentenceTransformerEmbeddingFunction` explicitly at collection create time.
- If some future builder genuinely needs onnxruntime, set `ORT_DISABLE_CPU_AFFINITY=1` in the environment and/or run under `numactl --cpunodebind=0 --membind=0`. Disabling HT in BIOS is the nuclear option.

**Runtime implication for python-stdlib:** The python-stdlib corpus was built with chromadb's onnxruntime default before the root cause was known. At runtime (`qira_search` / `qira_read`) the process is short-lived and low-concurrency, so the crash path has not been observed during search — but it is the same onnxruntime code path in principle. If python-stdlib ever gets rebuilt, switch it to `SentenceTransformerEmbeddingFunction` as well, and it would also let gotcha #2 below go away.

**Safety net (still in place, keep it):** `crash_log_open()` at `examples/eu-ai-act/build_corpus.py:40` writes fsync'd lines to `.build/crash.log`, and resume mode rebuilds ChromaDB from SQLite on restart (`rebuild_chroma_from_db`, `examples/eu-ai-act/build_corpus.py:991`). The crash is fixed, but the instrumentation is cheap and worth keeping for any future surprise.

## 2. ChromaDB embedding function mismatch between corpora

**Symptom:** opening a ChromaDB collection raises because the embedding function at read time doesn't match the one used at create time.

**Cause (historical):**
- `python-stdlib` was built with ChromaDB's default embedding function (onnxruntime, `all-MiniLM-L6-v2`) — before the crash root cause in gotcha #1 was understood.
- `eu-ai-act` is built with `SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")` (PyTorch) specifically to dodge the onnxruntime crash.
- Same model, different wrappers — ChromaDB treats them as different.

**Fix:** `runtime/qira` patches `_get_embedding_function()` at `runtime/qira:143` (uncommitted) to select the wrapper based on the `## Embedding` string in `corpus.md`. If it contains `sentence-transformers`, use `SentenceTransformerEmbeddingFunction`; otherwise fall back to ChromaDB default.

**Path forward — decision pending.** Two options: (A) rebuild `python-stdlib` with `SentenceTransformerEmbeddingFunction` so both corpora use PyTorch, or (B) rebuild `eu-ai-act` with chromadb's default and document `ORT_DISABLE_CPU_AFFINITY=1` as a required env var for affected hosts. Either path collapses the dispatcher. See `project_embedding_backend_decision.md` in memory for the full trade-off analysis. Do not execute either path until the user confirms. Design principle: QIRA uses exactly **one** embedding backend — see `feedback_qira_single_backend.md`.

**Hardcoded model name caveat:** the patch ignores the model portion of the `## Embedding` string and always returns `all-MiniLM-L6-v2`. Any future corpus using a different sentence-transformers model requires a runtime update.

## 3. ChromaDB has no WAL — must be wiped on resume

**Symptom:** rebuilding with existing `chroma/` dir can load a corrupt collection after an unclean shutdown.

**Fix:** `setup_output()` in `examples/eu-ai-act/build_corpus.py:949` **always** wipes `chroma/` (independent of `--fresh`) and rebuilds the collection from SQLite via `rebuild_chroma_from_db` (`build_corpus.py:991`). Do not optimize this away.

## 4. Questions are recoverable from SQLite

Every builder must ensure this holds: all questions stored in ChromaDB must also be recoverable from the `search_entry` column in SQLite so `rebuild_chroma_from_db` can work. The regex for extraction is `^- \*(.+)\*$` per line. If you add decoration around the question bullets, update the regex or break resume.

## 5. Cross-reference "double annotation" guard

`_rewrite_text` at `examples/eu-ai-act/build_corpus.py:823` checks for ` (see ` immediately following a match before rewriting, to prevent `Article 6 (see eu-ai-act:4.1.1) (see eu-ai-act:4.1.1)`. Same guard is needed in any new builder that runs multiple xref passes.

## 6. Silent skip on Chroma→SQLite mismatch in `qira_search`

`runtime/qira:207` continues if a `section_id` in ChromaDB has no matching SQLite row. This hides corruption: a build that wrote ChromaDB but failed to write SQLite will return fewer results than expected with no error. If search results look thin, check row counts:

```bash
sqlite3 {corpus}.db "SELECT count(*) FROM sections"
```

vs the ChromaDB collection count.

## 7. `keprompt` must be on PATH and `prompts/` dir must exist

`call_keprompt` at `examples/eu-ai-act/build_corpus.py:853` runs `subprocess.run(["keprompt", "chat", "new", ...])` with `cwd=keprompt_dir`. That directory must contain a `prompts/` subdir with the `.prompt` file. The builder's `main()` auto-detects this by looking for `./prompts/` relative to the script first, then to `cwd`. If neither exists, it aborts.

Per memory `feedback_keprompt_usage.md`: use prompt **names** not paths; run from the project dir.

## 8. `qira --initialize` only picks one worked example

`runtime/qira:334` iterates corpora and uses the **first** corpus's `## Example` section as `$worked_example`. If you want a different corpus to drive the example shown to the LLM, either reorder (alphabetical by directory name — see `list_corpora`) or change `initialize()`.

## 9. Section IDs: always full corpus-prefixed form

Easy to slip up when writing a new builder and emit `3.2.4` instead of `eu-ai-act:3.2.4` somewhere. The full prefixed form must appear in: `sections.id`, `metadata.section_id`, all markdown content, the `## Subsections` list in `read_entry`, rewritten xrefs. Grep for raw numeric IDs after a build as a sanity check.

## 10. Don't forget `corpus.md`

The builder must write `corpus.md` with all four `## ` headings (`Name`, `Description`, `Embedding`, `Example`). Without it, `qira --initialize` skips the corpus with a warning and it won't appear in the catalog.
