# QIRA — Question Indexed Retrieval Agent

**Structured knowledge retrieval for LLMs using question-to-question semantic search.**

QIRA is an alternative to RAG. Instead of chunking documents and hoping retrieval works, QIRA puts the LLM in control of retrieval as an agent. Documents are indexed by the *questions they answer*, not by arbitrary chunks. The LLM searches with a precise question, gets back structured pointers to relevant sections, and reads what it needs.

Read the paper: [QIRA_Article.md](QIRA_Article.md)

## Quick Start

QIRA runs as a [keprompt](https://github.com/JerryWestrick/keprompt) external function. To use it:

1. Download a corpus zip from [`corpus/`](corpus/)
2. Extract into your keprompt project's `prompts/functions/` directory
3. Run `qira --initialize` to generate `qira.prompt`
4. Add `.functions qira` and `.include functions/qira.prompt` to your prompts

That's it. The LLM can now search and read the corpus.

## Available Corpora

| Corpus | Description | Size |
|--------|-------------|------|
| [python-stdlib](corpus/python-stdlib.zip) | Python Standard Library — 10 modules, 598 sections, 5346 questions | 11 MB |

## Building Your Own Corpus

A QIRA corpus is a directory containing pre-formatted sections (SQLite) and a question index (ChromaDB). Building one means:

1. Parse your source documents into a section tree
2. Generate questions for each section using an LLM
3. Pre-format the storage entries
4. Vectorize and store

Each source format needs its own builder. See [`examples/python-stdlib/`](examples/python-stdlib/) for a reference implementation that parses CPython RST documentation.

The storage contract and architecture are documented in [`docs/`](docs/).

## Need a Corpus Built?

Building a high-quality corpus requires expertise — parsing structure from messy real-world documents, engineering good questions, validating retrieval quality. If you have docs that should be AI-accessible and want it done right, [get in touch](mailto:jerry@westrick.com).

- **Open source corpus builds** — your domain becomes part of the QIRA marketplace
- **Private corpus builds** — stays behind your firewall, full exclusivity

## Documentation

- [QIRA_Article.md](QIRA_Article.md) — The conceptual paper
- [docs/concept.md](docs/concept.md) — What QIRA is, why it exists
- [docs/architecture.md](docs/architecture.md) — System architecture
- [docs/design.md](docs/design.md) — Design decisions, storage contract
- [docs/qi-pipeline.md](docs/qi-pipeline.md) — Building corpora
- [docs/qi-ra-interface.md](docs/qi-ra-interface.md) — Storage contract spec
- [docs/prompt-template.md](docs/prompt-template.md) — How qira.prompt is generated
- [docs/competition-study.md](docs/competition-study.md) — Prior art and competitive landscape

## License

MIT — see [LICENSE](LICENSE)
