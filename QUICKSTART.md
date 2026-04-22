# QIRA Quickstart

Get a working QIRA setup from a cold install and verify it in two stages:

1. **Plumbing test** — pipe JSON into the qira runtime directly. No LLM, no keprompt. Validates the corpus is readable and the Python dependencies are installed correctly. Five minutes.
2. **Full test** — let a real LLM call `qira_search` via keprompt. Validates the whole retrieval loop. Five more minutes, plus an LLM account.

If plumbing fails, the corpus or the Python environment is the problem. If plumbing passes but the full test fails, the keprompt wiring or LLM credentials are the problem. The split lets you localize any failure fast.

## Prerequisites

- **Python 3.12 or later**, with `pip` and the `venv` module
- A terminal
- For the full test only: an API key for an LLM provider supported by [keprompt](https://github.com/JerryWestrick/keprompt) (OpenAI, Anthropic, Cerebras, etc.)

QIRA is not distributed as a Python package. It is a KePrompt external function plus a corpus directory. There is no `pip install qira`. You install keprompt, drop a corpus zip in the right place, and point the LLM at it.

## 1. Create a Workspace

```bash
mkdir ~/qira-test && cd ~/qira-test
python3 -m venv .venv
source .venv/bin/activate
```

The directory you are standing in is your **keprompt project directory**. After `pip install keprompt`, keprompt treats the current working directory as the project root.

> **Keep the venv activated** for every step below. The `qira` runtime has a generic `#!/usr/bin/env python3` shebang and inherits whichever `python3` is on PATH. If keprompt (or you) spawn `qira` from a shell where the venv is not active, `qira` will not find `chromadb` and will fail.

## 2. Install the Required Python Packages

```bash
pip install chromadb keprompt
```

Only two direct packages:

- **`chromadb`** — the vector store that the qira runtime opens to do question-to-question search. Transitively brings in `onnxruntime` (used by ChromaDB's default embedding function, which is what the `python-stdlib` corpus was built with) and ~70 other transitive dependencies. No manual dependency hunting required.
- **`keprompt`** — the LLM harness. Discovers external functions, routes tool calls to them, and runs conversations against whichever model you configure. Needed for project initialization (step 3) and for the **full test** (step 6); the plumbing test (step 5) does not use it.

> **Haswell-EP / Xeon E5 v3 note.** If your host is a dual-socket Xeon E5 v3 (Haswell-EP) with hyperthreading enabled, onnxruntime has a documented thread-affinity pattern that can trigger a "929 Fatal MCA" hardware errata and hard-reset the box under sustained parallel load. Single-call runtime usage (one `qira_search`, one `qira_read`) has not been observed to trigger it, but if it does, set `export ORT_DISABLE_CPU_AFFINITY=1` before invoking `qira` or keprompt.

## 3. Initialize the KePrompt Project

```bash
keprompt init
```

Run this once, in your project directory, after installing keprompt and before installing any corpus. `keprompt init` needs internet access — it downloads the LiteLLM model price database (~2,600 models) on first run.

After init, your project looks like this:

```
.
└── prompts
    ├── chats.db                              # SQLite chat history
    ├── functions
    │   ├── functions.json                    # function registry
    │   ├── keprompt_builtins.py              # keprompt's built-in functions
    │   ├── model_prices_and_context_window.json  # LiteLLM model DB
    │   └── render_url_to_markdown.py         # sample external function
    └── hello.prompt                          # starter prompt template
```

`prompts/functions/` is where KePrompt discovers external functions. In step 4 you will drop the `qira` executable (from the corpus zip) into this directory, alongside the files above.

## 4. Install a Corpus

Download a corpus zip and extract it into `prompts/functions/`. The zip contains the `qira` runtime executable *and* a `qira-corpus/{name}/` directory with the pre-built index. `unzip -d` will create `prompts/functions/` if `keprompt init` did not already.

```bash
# Example: python-stdlib corpus from the QIRA repo
curl -L -o /tmp/python-stdlib.zip \
  https://github.com/JerryWestrick/QIRA/raw/main/corpus/python-stdlib.zip
unzip /tmp/python-stdlib.zip -d prompts/functions/
chmod +x prompts/functions/qira
```

After extraction you should have:

```
prompts/
└── functions/
    ├── qira                            # runtime executable
    └── qira-corpus/
        └── python-stdlib/
            ├── corpus.md
            ├── python-stdlib.db
            └── chroma/
                ├── chroma.sqlite3
                └── <uuid>/...
```

## 5. Plumbing Test — No LLM, No KePrompt

This test validates that:

- The `qira` runtime executes in your fresh venv
- `chromadb` is importable (meaning step 2 worked)
- The corpus is readable
- Function discovery, search, and read all return valid markdown matching the QI/RA contract

No LLM. No keprompt. No tool-calling. Just pipe JSON to the executable and read what comes back.

### 5a. Function discovery

```bash
./prompts/functions/qira --list-functions
```

**Expected output** — a single JSON array describing two tools:

```json
[{"name": "qira_search", ...}, {"name": "qira_read", ...}]
```

If you see `ModuleNotFoundError: No module named 'chromadb'`, the venv is not activated. Run `source .venv/bin/activate` and retry.

### 5b. Search

Ask a question that the corpus obviously covers:

```bash
echo '{"corpus":"python-stdlib","question":"How do I pretty-print JSON?"}' \
  | ./prompts/functions/qira qira_search
```

**Expected output** — markdown with one or more `## -{distance}- python-stdlib:{id} {title}` headings, each followed by a `>` breadcrumb, bulleted italic questions, and a plain-text excerpt. Distances are floats (lower = better). Something like:

```
## -0.50- python-stdlib:1 json — JSON encoder and decoder
> Python Standard Library > json
- *What is the purpose of the `json` module...*
- *...*

**Source code:** `Lib/json/__init__.py`
...
```

First call is slow (a few seconds — ChromaDB loads the onnxruntime embedding model on startup). Subsequent calls in the same process are fast, but each invocation is a fresh process, so every plumbing-test call pays the cold-start cost.

### 5c. Read

Pick any section ID from the 5b output (for example `python-stdlib:1.1.2`) and read it:

```bash
echo '{"section_id":"python-stdlib:1.1.2"}' \
  | ./prompts/functions/qira qira_read
```

**Expected output** — markdown starting with an `# {id} {title}` heading (h1, not h2 — h1 means "full read", h2 means "search hit"), followed by the breadcrumb and the full section content:

```
# python-stdlib:1.1.2 dumps
> Python Standard Library > json > Basic Usage > dumps

`dumps(obj, *, skipkeys=False, ...)`

Serialize *obj* to a JSON formatted `str`...
```

**Plumbing test passes if 5a, 5b, and 5c all return valid markdown with no errors and no host crash.** At this point you have proved:

- The corpus zip is a valid QIRA corpus
- Your Python environment can run the qira runtime
- Every piece of the QI/RA storage contract (SQLite schema, ChromaDB schema, markdown formats) is intact end-to-end

## 6. Full Test — LLM + KePrompt

This test validates the entire retrieval loop: an LLM reads a user question, decides to call `qira_search`, keprompt spawns the qira runtime to execute the call, the markdown result is handed back to the LLM, and the LLM produces an answer that cites section IDs from the corpus.

### 6a. Generate `qira.prompt`

The `qira.prompt` file is the instructions the LLM reads to learn how to use QIRA. It is regenerated from each corpus's `corpus.md` on every run of `--initialize`:

```bash
./prompts/functions/qira --initialize
```

**Expected output** — `Generated .../prompts/functions/qira.prompt`. Check the file contents if you want to see what the LLM will actually be told about the available corpora.

### 6b. Configure LLM Credentials

Set the environment variable for your chosen provider. For example:

```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
# or
export CEREBRAS_API_KEY=csk-...
```

Consult keprompt's documentation for the authoritative list of supported providers and the corresponding env var names.

### 6c. Write a Test Prompt

Create `prompts/test.prompt`:

```
.prompt "name":"qira-plumbing-test", "version":"1.0", "params":{"model":"openai/gpt-4o-mini"}
.functions qira.*
.system You are a helpful assistant. When a user question could be answered from an available corpus, use qira_search and qira_read to ground your answer and cite the section IDs.
.include prompts/functions/qira.prompt
.user Using the provided documentation; Lookup how do I pretty-print JSON in Python, and which parameters of json.dumps control the output formatting?
.exec
```

A few things to note about this prompt:

- **`.functions qira.*`** uses a wildcard to match every function keprompt discovered that starts with `qira` — namely `qira_search` and `qira_read`. Without the wildcard, `.functions qira` would look for a single function literally named `qira` and not find the two we want.
- **`.functions` comes before `.system`.** Function declarations are part of the model's setup and must be declared before any system or user messages.
- **`.include prompts/functions/qira.prompt`** uses the full path from your project root, not a path relative to the `prompts/` directory.
- The `.user` question says "Using the provided documentation; Lookup how do I..." — explicit framing nudges the LLM to actually exercise the tools rather than answer from its own training data.

Swap `openai/gpt-4o-mini` for any model your provider supports that can call tools.

### 6d. Run It

```bash
keprompt chat new --prompt test
```

**Expected behavior** — keprompt loads the routines in `prompts/functions/` (you will see a line like `[FunctionSpace] Loaded 7 routines from 'prompts/functions'`), sends the prompt plus the function definitions to the LLM, and the LLM responds by calling `qira_search`. KePrompt spawns `qira qira_search` as a subprocess, gets markdown back, feeds it to the LLM, and the LLM issues one or more `qira_read` calls before producing an answer. A capable model will often issue multiple `qira_read` calls in parallel.

The run ends with a cost summary and the answer panel, something like:

```
Chat 24820074:1 with openai:openai/gpt-4o-mini Total Cost: $0.000739 (In: $0.000538, Out: $0.000200) Wall: 15.06s API: 11.84s
Context: Input 3,588/128,000 (2.8%) Output 334/16,384 (2.0%)
```

The final answer should cite at least one `python-stdlib:...` section ID.

**Full test passes if:**

- KePrompt discovered the qira functions without error (`Loaded N routines` line shows a non-zero count and no error)
- The LLM called `qira_search` at least once (confirmable via `keprompt chat show`)
- The LLM called `qira_read` at least once
- The LLM's final answer references at least one section ID from the corpus (e.g. `python-stdlib:1.1.2`)

**Inspect the full trace.** KePrompt records the whole conversation. To see every message, tool call, tool result, cost, and VM state, run:

```bash
keprompt chat show {chat_id}
```

where `{chat_id}` is the number printed in the summary line (e.g. `24820074`). The `messages` array shows the exact arguments the LLM passed to `qira_search` and `qira_read`, and the exact markdown it received back. This is the authoritative plumbing-level trace — use it to debug any mismatch between what you expect and what the LLM actually did.

**This does not test answer correctness.** Answer correctness is corpus-specific and subjective — see the Notes section at the bottom. The full test is a plumbing test, just with more plumbing.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'chromadb'` | venv not active when `qira` was invoked | `source .venv/bin/activate`, retry |
| `qira: command not found` | Wrong working directory, or `chmod +x` was skipped | `cd ~/qira-test && chmod +x prompts/functions/qira` |
| `Error: unknown corpus 'python-stdlib'. Available: ` | Zip extracted to the wrong location, or `qira-corpus/` is missing | Re-extract with `unzip ... -d prompts/functions/` |
| `Error: section 'python-stdlib:1.1.2' not found` | Section ID copy-paste error, or corpus was built against an older ID scheme | Verify the ID from a fresh `qira_search` result |
| Host hard-reset during plumbing test | Haswell-EP / Xeon E5 v3 929 MCA errata (onnxruntime pinning across HT siblings) | Disable hyperthreading in BIOS. `ORT_DISABLE_CPU_AFFINITY=1` alone is not sufficient under concurrent load. |
| LLM never calls any qira function | Model does not support tool/function calling, or the user question does not obviously need the corpus | Use a model that supports tools; ask a question that is clearly covered by the corpus; nudge the user message with "Using the provided documentation; Lookup ..." |
| `.functions qira` declared but the LLM can't see `qira_search`/`qira_read` | Bare name `qira` looks for a single function literally called `qira`, not a prefix | Use the wildcard form: `.functions qira.*` |
| `ImportError` involving `onnxruntime` on an older CPU | CPU lacks AVX instructions onnxruntime requires | Upgrade hardware, or rebuild the corpus locally against a different embedding backend |

## Notes

- **QIRA is a principle, not a Python package.** The deliverable is the pattern: question-indexed retrieval, LLM-driven, corpus directories, the QI/RA storage contract. The `runtime/qira` executable and the reference corpora in this repo are a practical, usable demonstration of that principle as a KePrompt external function. Other implementations are possible. See [docs/](docs/) for the design documents.
- **Correctness is not tested here.** Whether the LLM gives a *good* answer depends on the corpus, the model, the prompt template, and the user's question. That is not a property QIRA itself can guarantee, and is not covered by the Quickstart. The Quickstart tests only that the plumbing is intact — given a good corpus and a good model, the pipes connect correctly.
- **One plumbing test, many corpora.** If you install multiple corpus zips into the same `prompts/functions/qira-corpus/` directory, rerun `qira --initialize` and repeat step 5b with each corpus name. The runtime handles them independently.
- **Upgrading the runtime.** When you replace a corpus zip, the `qira` executable is overwritten too. If multiple zips contain different versions, the one extracted last wins. All shipped corpora use the same embedding backend (ChromaDB default, onnxruntime `all-MiniLM-L6-v2`), so any version of the runtime that matches the contract will serve any of them.
