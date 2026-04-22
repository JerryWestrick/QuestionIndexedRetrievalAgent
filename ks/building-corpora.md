# Building Corpora (QI Pipeline)

**Spec:** `docs/qi-pipeline.md` + `docs/qi-ra-interface.md`. This file condenses them and maps the 8-step pipeline onto the two reference builders.

## The 8 steps

| # | Step | Adapter or shared? |
|---|---|---|
| 1 | Parse source → section tree | **Format-specific** (per-format adapter) |
| 2 | Convert to markdown preserving structure | **Format-specific** (last format-specific step) |
| 3 | Organize — assign hierarchical IDs, build breadcrumbs, determine readable unit depth | Shared |
| 4 | Rewrite cross-references to full corpus-prefixed IDs | **Semi-shared** — detection patterns are format-specific, write-back logic is shared |
| 5 | Generate questions per readable unit (LLM call, one per section) | Shared (KePrompt invocation pattern) |
| 6 | Pre-format `search_entry` + `read_entry` markdown per section | Shared |
| 7 | Vectorize questions with Model2Vec and append to FAISS `IndexFlatL2` | Shared |
| 8 | Write sections + questions to SQLite, write `{corpus}.faiss`, write `corpus.md` | Shared |

**Adapter boundary:** steps 1-2. After step 2 the pipeline is identical regardless of source format. Copy-paste the shared-infrastructure functions between builders.

## Reference builders

### `examples/python-stdlib/`

| Item | Value |
|---|---|
| Source format | CPython RST (Sphinx-flavored reStructuredText) |
| Parser | `docutils` |
| Xref rewriting | `:func:` / `:class:` / `:mod:` role lookups → IDs |
| Builder | `examples/python-stdlib/build_corpus.py` (880 lines) |
| Question prompt | `examples/python-stdlib/generate_questions.prompt` |
| Embedding model | Model2Vec `minishlab/potion-base-8M` (static, CPU-only) |
| LLM for Q-gen | `cerebras/gpt-oss-120b` via KePrompt |
| Production numbers | 10 modules, 598 sections, 5346 questions, <$0.29, <30 min single-threaded |
| Output | Shipped as `corpus/python-stdlib.zip` (11 MB) |
| README | `examples/python-stdlib/README.md` |

Source acquisition:
```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/python/cpython.git cpython-docs
cd cpython-docs && git sparse-checkout set Doc/library
```

### `examples/eu-ai-act/`

| Item | Value |
|---|---|
| Source format | EUR-Lex Formex 4 XML (CELEX 32024R1689) |
| Parser | `xml.etree.ElementTree` |
| Xref rewriting | Regex over plain-text `Article N(M)` / `Annex III` / `Chapter IV` / `Recital (N)` → `{orig} (see eu-ai-act:{id})`. Formex doesn't mark up intra-doc xrefs. |
| Builder | `examples/eu-ai-act/build_corpus.py` (1340 lines) |
| Question prompt | `examples/eu-ai-act/generate_questions.prompt` |
| Embedding model | Model2Vec `minishlab/potion-base-8M` — same as python-stdlib (single backend across all corpora) |
| LLM for Q-gen | `cerebras/gpt-oss-120b` via KePrompt |
| Estimated cost | ~400 sections × ~$0.0007 ≈ $0.30 |
| Status | Shipped — corpus zip at `corpus/eu-ai-act.zip` |
| README | `examples/eu-ai-act/README.md` |

Source acquisition:
```bash
curl -sSL -H "Accept: application/zip" -o fmx.zip \
  "http://publications.europa.eu/resource/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1.0006.02/DOC_1"
unzip fmx.zip
```

## Key builder functions (eu-ai-act as the more recent reference)

All line numbers refer to `examples/eu-ai-act/build_corpus.py`.

| Function | Line | Purpose |
|---|---|---|
| `crash_log_open` / `crash_log` | 40-53 | fsync'd append-log that survives hard resets. Every major step writes one line. |
| `render_inline` | 87 | Formex inline elements → markdown inline. |
| Section parsing (main act, annexes) | varies | XML walk building the `Section` dataclass tree. |
| `organize` (called from `main`) | 1210 area | Step 3 — assigns IDs and breadcrumbs. |
| `_assign_ids` | 750 | Recursive ID assignment. |
| `build_xref_maps` | 761 | Step 4a — build lookup tables. |
| `_XREF_PATTERNS` | 798 | Step 4b — regex patterns for cross-ref detection. |
| `rewrite_xrefs` / `_rewrite_text` | 810 / 823 | Step 4c — regex substitution with "already annotated" guard. |
| `call_keprompt` | 853 | Step 5 — one subprocess call per section. 180s timeout. Falls back to stub on failure. |
| `build_section_entries` | 912 | Step 6 — pre-format `search_entry` + `read_entry`. |
| `setup_output` | 962 | Step 7/8 — create output dir, open SQLite (`CREATE TABLE sections` + `CREATE TABLE questions`), return `(conn, db_path, faiss_path)`. Wipes DB + `.faiss` if `fresh=True`. |
| `_backfill_questions_from_search_entry` | 1003 | Legacy-corpus migration — if `questions` is empty but `sections` is populated, extracts questions from each `sections.search_entry` via regex `^- \*(.+)\*$` and populates `questions`. |
| `rebuild_faiss_from_db` | 1032 | **Resume path** — loads Model2Vec, creates in-memory `IndexFlatL2`, re-encodes every `questions.question` in `idx` order, returns `(index, count)`. SQLite is the source of truth; FAISS is always rebuilt in memory and written to disk only at end of successful build. |
| `write_corpus_md` | 1021 | Write `corpus.md` with Name/Description/Embedding/Example. |
| `process_section` | 1052 | Worker: keprompt → format → persist under `write_lock`. |
| `main` | 1140 | Arg parsing, orchestration. |

## Builder CLI (eu-ai-act)

```
build_corpus.py --source DIR --output DIR
                [--skip-questions]    # use stub questions, no LLM calls
                [--parallel N]        # default 10; forced to 1 if --skip-questions
                [--fresh]             # wipe SQLite; default is resume
                [--print-tree]        # print parsed tree and exit
                [--limit N]           # only first N top-level sections
                [-y | --yes]          # skip cost confirmation prompt
```

Resume semantics: default is resume. SQLite rows are preserved; the in-memory FAISS index is **always** rebuilt from the SQLite `questions` table on each run via `rebuild_faiss_from_db`, and the `.faiss` file is written only at end of a successful run. SQLite is the source of truth.

## Running a build

python-stdlib:
```bash
cd examples/python-stdlib
../../.venv/bin/python3 build_corpus.py \
  --source /tmp/cpython-docs/Doc/library \
  --output ../../test-corpus/python-stdlib
```

eu-ai-act:
```bash
cd examples/eu-ai-act
../../.venv/bin/python3 build_corpus.py \
  --source .build/source \
  --output .build/corpus/eu-ai-act
```

## KePrompt integration

The builder calls `keprompt chat new --prompt generate_questions --set breadcrumb ... --set title ... --set content ...`. `keprompt` must be on PATH. The `generate_questions.prompt` file must be in a `prompts/` subdir of the CWD at invocation time. Output is JSON with `ai_response` as a newline-separated list of questions.

## Writing a new builder

1. Copy an existing `build_corpus.py` as a starting point
2. Rewrite steps 1-2 (parse + render) for the new format
3. Set `CORPUS = "your-corpus-id"`
4. Tune `_XREF_PATTERNS` and the xref map builder for the new format
5. Update `write_corpus_md()` Name/Description/Example
6. Keep the shared infrastructure (`setup_output`, `build_section_entries`, `rebuild_faiss_from_db`, `process_section`) unchanged unless the contract changes
7. Write a sibling `generate_questions.prompt`
8. Validate: `--print-tree` first, then `--skip-questions` full run, then full build with `--limit`, then full production build
