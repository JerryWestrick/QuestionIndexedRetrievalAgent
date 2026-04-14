# Repo Layout

QIRA = Question Indexed Retrieval Agent. RAG replacement. LLM drives retrieval; documents indexed by questions-they-answer, not content.

Delivery model (per memory): corpus zips as product, no pip package, marketplace + build consultancy.

## Top-level

| Path | Purpose |
|---|---|
| `README.md` | Human entry point. Quick start, available corpora, build-a-corpus pitch. |
| `LICENSE` | MIT. |
| `QIRA_Article.md` / `.pdf` | The conceptual paper. Source of the "RAG is hope-based" framing. |
| `docs/` | Human design docs. `concept → architecture → design → qi-pipeline → qi-ra-interface → prompt-template` + `competition-study`. |
| `ks/` | This directory. Claude-oriented shared understanding. |
| `runtime/` | The QIRA runtime. Single file: `runtime/qira` (Python, KePrompt external function). |
| `corpus/` | Distributable corpus zips. Currently: `python-stdlib.zip` (11 MB, onnxruntime default), `eu-ai-act.zip` (25 MB, sentence-transformers). Both **uncommitted**. |
| `examples/` | Reference QI builders, one per source format. |
| `.venv/` | Project virtualenv. Has `chromadb`, `sentence-transformers`, `docutils`, etc. |
| `.claude/settings.local.json` | Project-level Claude Code settings. |

## `docs/` — human design layer

| File | What it covers |
|---|---|
| `concept.md` | Elevator pitch. 33 lines. Read to LLM framing. |
| `architecture.md` | System overview, QI + RA pipelines, tool interface, 6 key decisions. |
| `design.md` | KePrompt integration, dir structure, storage contract, runtime impl steps, error handling. |
| `qi-pipeline.md` | 8 QI steps; adapter boundary (steps 1-2 format-specific, 3-8 shared). |
| `qi-ra-interface.md` | **THE contract.** Non-negotiable spec between QI producers and RA consumers. ks/contract.md condenses this. |
| `prompt-template.md` | `qira.prompt` template used by `--initialize`. |
| `competition-study.md` | Prior art: QuIM-RAG, HyPE, FLARE, RAPTOR, GraphRAG etc. |

## `runtime/qira`

Single executable. 428 lines (pre-patch). See **ks/runtime.md** for details.

Entry points:
- `--list-functions` — OpenAI function defs for KePrompt discovery
- `--initialize` — scan corpus dirs, generate `qira.prompt`
- `--version`
- `qira_search` / `qira_read` — read JSON from stdin, write markdown to stdout

## `examples/`

Each example is a **self-contained reference QI builder** for one source format. Copy-paste the shared-infrastructure sections, write the format-specific parser at the top.

| Dir | Source format | Status |
|---|---|---|
| `examples/python-stdlib/` | CPython RST docs via `docutils` | Built. Corpus zip shipped in `corpus/python-stdlib.zip`. `build_corpus.py` is 880 lines. |
| `examples/eu-ai-act/` | EUR-Lex Formex 4 XML | **Build complete, corpus zip built and plumbing-validated.** 404 sections, 13,012 questions. Builder is 1340 lines. Uncommitted (gitignored `.build/` dir + modified runtime + corpus/eu-ai-act.zip). Ship gated on embedding-backend decision — see `project_embedding_backend_decision.md` in memory. |

Each example dir has:
- `build_corpus.py` — the builder
- `generate_questions.prompt` — KePrompt prompt for LLM question generation
- `README.md` — human walkthrough
- `.build/` (eu-ai-act only, gitignored) — `source/`, `corpus/`, `build.log`, `crash.log`

## Runtime vs build dependency direction

```
Source docs ──► [example builder] ──► corpus dir (SQLite + chroma/ + corpus.md)
                                              │
                                              ▼
                                       runtime/qira  (reads corpus dir)
                                              │
                                              ▼
                                        LLM via KePrompt
```

The runtime knows nothing about builders. Builders know nothing about the runtime except the contract (`ks/contract.md`). The boundary is the corpus directory shape.
