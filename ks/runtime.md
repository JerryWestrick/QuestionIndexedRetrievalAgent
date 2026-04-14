# runtime/qira — behavior reference

Single file: `runtime/qira` (executable Python, ~440 lines including uncommitted patch). KePrompt external function.

Imports: `chromadb`, `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction`, `sqlite3`, `json`, `pathlib`, `string.Template`.

## CLI modes

| Invocation | What it does | Code |
|---|---|---|
| `qira --list-functions` | Print `FUNCTION_DEFINITIONS` JSON (OpenAI function-calling format). Called by KePrompt during function discovery. | `runtime/qira:63` |
| `qira --version` | Print `qira 0.1.0`. | `runtime/qira:398` |
| `qira --initialize` | Scan `qira-corpus/` → read each `corpus.md` → write `qira.prompt` next to the script. Release-time tool. | `runtime/qira:334` |
| `qira qira_search` | Read JSON from stdin → call `qira_search()` → print markdown. | `runtime/qira:174` |
| `qira qira_read` | Read JSON from stdin → call `qira_read()` → print markdown. | `runtime/qira:224` |

## Function definitions

Defined in `FUNCTION_DEFINITIONS` at `runtime/qira:63`:

- **`qira_search(corpus, question, n_results=5)`** — required: `corpus`, `question`; optional: `n_results` (int, default 5).
- **`qira_read(section_id)`** — required: `section_id`, format `{corpus}:{hierarchy}`.

`additionalProperties: False` on both.

## Corpus directory discovery

`find_corpus_dir()` at `runtime/qira:34` resolves `CORPUS_DIR` once at import time. Search order:

1. `{script_dir}/qira-corpus` — normal install (when `runtime/qira` is dropped into `prompts/functions/`, corpus sits next to it)
2. `{cwd}/qira-corpus` — dev/testing
3. `{cwd}/test-corpus` — dev/testing
4. `{script_dir.parent}/test-corpus` — dev/testing

Returns `None` if none exist. `initialize()` and all corpus opens fail loudly if `CORPUS_DIR is None`.

`list_corpora()` at `runtime/qira:120` lists every subdirectory of `CORPUS_DIR` that contains `{name}/{name}.db`.

## Search flow — `qira_search` (`runtime/qira:174`)

1. `open_chroma(corpus)` → PersistentClient + collection (see embedding note below)
2. `open_db(corpus)` → sqlite3 connection with `row_factory = Row`
3. `collection.query(query_texts=[question], n_results=n_results, include=["metadatas", "distances"])` — ChromaDB embeds the query using its stored embedding function
4. Dedupe: group by `metadata.section_id`, keep lowest distance per section
5. Sort by distance ascending; for each, `SELECT title, search_entry FROM sections WHERE id = ?`
6. Assemble: `f"## -{dist:.2f}- {sid} {row['title']}\n{row['search_entry']}"`, join with `\n\n`, trailing `\n`
7. Empty result → `"## Nothing Found\n"`

Silent skip if a `section_id` in Chroma has no matching SQLite row (could hide corruption — caller doesn't know).

## Read flow — `qira_read` (`runtime/qira:224`)

1. Validate `section_id` contains `:` — else `ValueError`
2. Split on first `:` → `corpus`, `hierarchy`
3. Open SQLite for `corpus`
4. `SELECT read_entry FROM sections WHERE id = ?` — with the **full** ID including prefix (not just hierarchy)
5. Missing → `ValueError("section '{id}' not found")`
6. Return `read_entry` verbatim

## Embedding function selection — the subtle bit

`_get_embedding_function(corpus)` at `runtime/qira:143` (uncommitted, in working tree):

1. Read `corpus.md`, parse sections
2. Look at the `Embedding` section string
3. If it contains `sentence-transformers` (case-insensitive), return `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")` — **hardcoded model name regardless of what `corpus.md` says**
4. Otherwise return `None` → ChromaDB falls back to its default (onnxruntime with `all-MiniLM-L6-v2`)

`open_chroma(corpus)` at `runtime/qira:156` passes the resolved function into `get_collection("questions", embedding_function=ef)` if non-None.

**Gotcha:** the collection must be opened with the **same** embedding function it was created with, or ChromaDB raises. The python-stdlib corpus was built with the chromadb default (onnxruntime); the eu-ai-act corpus is built with `SentenceTransformerEmbeddingFunction` (PyTorch). The patch in the working tree lets the runtime serve both. See `ks/gotchas.md`.

## `--initialize` — prompt generation

`initialize()` at `runtime/qira:334`:

1. Must have `CORPUS_DIR` and at least one corpus — else exit 1
2. For each corpus: read `corpus.md`, parse via `parse_corpus_md()` at `runtime/qira:312` (splits on `## ` headings)
3. Build `corpus_table` row: `| {corpus_name} | {Name} — {Description} |`
4. Take `worked_example` from the **first** corpus with an `## Example` section
5. `PROMPT_TEMPLATE.substitute(...)` — see `runtime/qira:255` for the template body (Python `string.Template`, `$variable` substitution)
6. Write `{script_dir}/qira.prompt`
7. Print the generated path

Template spec matches `docs/prompt-template.md`.

## Error protocol (KePrompt external function convention)

- **Success** → stdout, exit 0
- **Expected errors** (unknown corpus, missing section, bad JSON) → stderr `Error: ...`, exit 1
- **Any exception** → caught in `main()` at `runtime/qira:386`, printed as `Error: {e}` to stderr, exit 1

KePrompt delivers the stderr text back to the LLM as a `tool_result`, so error messages should read well to an LLM.

## Outputs to remember verbatim

- Empty search: `## Nothing Found\n`
- Heading format: `## -{dist:.2f}- {id} {title}` — two digits after the decimal, negative sign as a literal dash prefix

## Known quirks

1. **Hardcoded embedding model name.** `_get_embedding_function` ignores the model part of the `Embedding` string and always returns `all-MiniLM-L6-v2`. OK as long as every sentence-transformers corpus uses that model. Not OK if a future corpus uses a different one.
2. **No connection reuse.** Every `qira_search` / `qira_read` call reopens SQLite and ChromaDB. Each KePrompt external-function invocation is a fresh process, so this is actually fine.
3. **`open_chroma` doesn't close the client.** `PersistentClient` holds no open file handles between calls, so this is fine in the fresh-process model above. Would leak in a long-running context.
4. **Silent skip on Chroma→SQLite mismatch** (noted in search flow above).
