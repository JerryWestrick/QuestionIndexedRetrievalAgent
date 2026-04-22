# runtime/qira — behavior reference

Single file: `runtime/qira` (executable Python, ~420 lines). KePrompt external function.

Imports: `faiss`, `numpy`, `sqlite3`, `json`, `pathlib`, `string.Template`. Model loading is lazy — `model2vec.StaticModel.from_pretrained(EMBEDDING_MODEL)` only runs when `qira_search` is called (not for `qira_read` or `--initialize`).

## CLI modes

| Invocation | What it does | Code |
|---|---|---|
| `qira --list-functions` | Print `FUNCTION_DEFINITIONS` JSON (OpenAI function-calling format). Called by KePrompt during function discovery. | `runtime/qira:68` |
| `qira --version` | Print `qira 0.2.0`. | `runtime/qira:388` |
| `qira --initialize` | Scan `qira-corpus/` → read each `corpus.md` → write `qira.prompt` next to the script. Release-time tool. | `runtime/qira:323` |
| `qira qira_search` | Read JSON from stdin → call `qira_search()` → print markdown. | `runtime/qira:162` |
| `qira qira_read` | Read JSON from stdin → call `qira_read()` → print markdown. | `runtime/qira:213` |

## Function definitions

Defined in `FUNCTION_DEFINITIONS` at `runtime/qira:68`:

- **`qira_search(corpus, question, n_results=5)`** — required: `corpus`, `question`; optional: `n_results` (int, default 5).
- **`qira_read(section_id)`** — required: `section_id`, format `{corpus}:{hierarchy}`.

`additionalProperties: False` on both.

## Corpus directory discovery

`find_corpus_dir()` at `runtime/qira:43` resolves `CORPUS_DIR` once at import time. Search order:

1. `{script_dir}/qira-corpus` — normal install (when `runtime/qira` is dropped into `prompts/functions/`, corpus sits next to it)
2. `{cwd}/qira-corpus` — dev/testing
3. `{cwd}/test-corpus` — dev/testing
4. `{script_dir.parent}/test-corpus` — dev/testing

Returns `None` if none exist. `initialize()` and all corpus opens fail loudly if `CORPUS_DIR is None`.

`list_corpora()` at `runtime/qira:125` lists every subdirectory of `CORPUS_DIR` that contains `{name}/{name}.db`.

## Storage files per corpus

| File | Purpose |
|---|---|
| `{corpus}/{corpus}.db` | SQLite. `sections` (id, title, search_entry, read_entry) + `questions` (idx, section_id, question). |
| `{corpus}/{corpus}.faiss` | FAISS `IndexFlatL2` file. Row `i` = vector for the question with `questions.idx = i`. |
| `{corpus}/corpus.md` | Corpus identity markdown: `## Name`, `## Description`, `## Embedding`, `## Example`. |

## Embedding model

Single hardcoded constant at `runtime/qira:29`:

```python
EMBEDDING_MODEL = "minishlab/potion-base-8M"
```

Loaded lazily via `_get_model()` at `runtime/qira:35` — `from model2vec import StaticModel; StaticModel.from_pretrained(...)`. Model2Vec is a distilled static embedding (no neural network inference at query time, just token lookup + pooling). No PyTorch, no onnxruntime, no CUDA. CPU-only, ~milliseconds to encode a query.

The **indexing model and the retrieval model must match.** The builder encodes questions with this same constant; the runtime encodes the query with it. Vector-space alignment is implicit in using the same `EMBEDDING_MODEL` string.

## Search flow — `qira_search` (`runtime/qira:162`)

1. `open_db(corpus)` → sqlite3 connection with `row_factory = Row`
2. `open_index(corpus)` → `faiss.read_index({corpus}.faiss)`
3. `model.encode([question]).astype(np.float32)` → 1×dim float32 query vector
4. `index.search(qv, n_results)` → `(D, I)` — L2 distances and FAISS row indices. FAISS returns `-1` for missing slots if the index has fewer than `n_results` vectors.
5. For each `(idx, dist)` pair: `SELECT section_id FROM questions WHERE idx = ?` — maps FAISS row → section ID
6. Dedupe: group by `section_id`, keep lowest distance per section
7. Sort by distance ascending; for each, `SELECT title, search_entry FROM sections WHERE id = ?`
8. Assemble: `f"## -{dist:.2f}- {sid} {row['title']}\n{row['search_entry']}"`, join with `\n\n`, trailing `\n`
9. Empty result → `"## Nothing Found\n"`

**Silent skip** at two points: an `idx` with no `questions` row is skipped; a `section_id` with no `sections` row is skipped. Both hide build corruption — see `ks/gotchas.md` #5.

## Read flow — `qira_read` (`runtime/qira:213`)

1. Validate `section_id` contains `:` — else `ValueError`
2. Split on first `:` → `corpus`, `hierarchy`
3. Open SQLite for `corpus`
4. `SELECT read_entry FROM sections WHERE id = ?` — with the **full** ID including prefix (not just hierarchy)
5. Missing → `ValueError("section '{id}' not found")`
6. Return `read_entry` verbatim

No FAISS involvement — `qira_read` is a pure SQLite lookup.

## `--initialize` — prompt generation

`initialize()` at `runtime/qira:323`:

1. Must have `CORPUS_DIR` and at least one corpus — else exit 1
2. For each corpus: read `corpus.md`, parse via `parse_corpus_md()` at `runtime/qira:301` (splits on `## ` headings)
3. Build `corpus_table` row: `| {corpus_name} | {Name} — {Description} |`
4. Take `worked_example` from the **first** corpus with an `## Example` section
5. `PROMPT_TEMPLATE.substitute(...)` — see `runtime/qira:244` for the template body (Python `string.Template`, `$variable` substitution)
6. Write `{script_dir}/qira.prompt`
7. Print the generated path

Template spec matches `docs/prompt-template.md`.

## Error protocol (KePrompt external function convention)

- **Success** → stdout, exit 0
- **Expected errors** (unknown corpus, missing section, bad JSON) → stderr `Error: ...`, exit 1
- **Any exception** → caught in `main()` at `runtime/qira:374`, printed as `Error: {e}` to stderr, exit 1

KePrompt delivers the stderr text back to the LLM as a `tool_result`, so error messages should read well to an LLM.

## Outputs to remember verbatim

- Empty search: `## Nothing Found\n`
- Heading format: `## -{dist:.2f}- {id} {title}` — two digits after the decimal, negative sign as a literal dash prefix

## Known quirks

1. **No connection reuse.** Every `qira_search` / `qira_read` call reopens SQLite and re-reads the FAISS index. Each KePrompt external-function invocation is a fresh process, so this is actually fine — FAISS index load is fast (mmap-backed) and Model2Vec load is ~100 ms.
2. **Silent skip on FAISS→SQLite mismatch** (see `ks/gotchas.md` #5).
3. **`_MODEL` module-level cache** is process-local. Doesn't matter in the fresh-process model. Would need rework for a long-running server.
