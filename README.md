# QIRA — Question Indexed Retrieval Agent

An architectural alternative to RAG for **structured** corpora. Instead of chunking documents and embedding the fragments, QIRA indexes documents by the *questions they answer* and lets the LLM drive retrieval as an agent — searching with precise questions, getting back structured pointers, and reading what it needs.

## Read the paper first

**→ [QIRA_Article.md](QIRA_Article.md)** ([PDF](QIRA_Article.pdf))

The paper is the primary artifact in this repository. It lays out the critique of RAG, the architectural inversion, a worked example, the cost economics, prior art, and limitations. Everything else here — runtime, corpora, builders, knowledge store — exists so the paper's claims can be independently verified.

The §2 scope caveat is load-bearing: RAG remains the only option for genuinely unstructured input (web scrape, OCR'd PDFs, chat logs). QIRA's claim is narrower — *when* documents have structure, use it.

## Reference cases — test it yourself

Two corpora ship with the repo as runnable evidence. Each is a self-contained zip — the runtime executable plus the pre-built index — that drops into a keprompt project's `prompts/functions/` directory.

| Corpus | Source | Sections | Questions | Size |
|---|---|---|---|---|
| [eu-ai-act](corpus/eu-ai-act.zip) | EU AI Act (Regulation 2024/1689), EUR-Lex Formex 4 XML | 404 | 13,012 | 13 MB |
| [python-stdlib](corpus/python-stdlib.zip) | Python Standard Library, Sphinx RST | 598 | 5,346 | 5.3 MB |

Use `eu-ai-act` if you want to see QIRA add value the LLM doesn't already have — the regulation post-dates most public training cutoffs. Use `python-stdlib` to confirm retrieval quality against material you can sanity-check by eye; expect the LLM to know most of it already.

[**QUICKSTART.md**](QUICKSTART.md) walks through installation and a two-stage validation: a plumbing test that pipes JSON to the runtime directly (no LLM needed), and a full test that runs an LLM through the retrieval loop. There is also a one-shot installer for the EU AI Act corpus:

```bash
curl -L https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/examples/eu-ai-act/try-eu-ai-act.sh | bash
```

[**Appendix A** of the paper](QIRA_Article.md#appendix-a-reproduce-the-6-runs) is the reproducibility kit for the §6 worked example — same prompt, same corpus, your own LLM choice.

## Build your own corpus

A QIRA corpus is a directory with pre-formatted sections (SQLite) and a question index (FAISS), conforming to the QI/RA storage contract. Each source format needs its own builder; the post-parse pipeline is shared.

Entry point: **[`ks/`](ks/)** — the knowledge store. It has an audience-split load order; corpus authors follow Path A, which whitelists the right files in the right order. The two reference builders under [`examples/`](examples/) are the starting points to copy from (`python-stdlib` for RST, `eu-ai-act` for XML).

Builders are bespoke per source format — standalone scripts, not a framework. The contract is the deliverable; how you produce it is your call.

## Consulting

For organizations with structured documents that need to be LLM-accessible — internal documentation, regulatory or compliance text, large technical references, domain-specific knowledge bases — corpus build engagements are available as consulting work. Open-source builds for public corpora; private builds stay behind your firewall. Contact: [jerry@westrick.com](mailto:jerry@westrick.com).

## Status

QIRA is at the **validated** stage, not the measured stage. The architectural inversion works on real corpora, demonstrably; the paper does not present a benchmark study. See [§8 Limitations](QIRA_Article.md#8-limitations) for what that means in practice (N=1 worked example, no head-to-head benchmark, two corpora both well-structured, LLM-generated index unvalidated, single-author, harness-coupled to keprompt).

Issues, corrections, and prior-art pointers welcome.

## Documentation

- [QIRA_Article.md](QIRA_Article.md) — the paper
- [QUICKSTART.md](QUICKSTART.md) — install and validation
- [`ks/`](ks/) — knowledge store, entry point for corpus authors and contributors
- [`docs/`](docs/) — human-readable design documents:
  [concept](docs/concept.md) ·
  [architecture](docs/architecture.md) ·
  [design](docs/design.md) ·
  [QI pipeline](docs/qi-pipeline.md) ·
  [QI/RA interface](docs/qi-ra-interface.md) ·
  [prompt template](docs/prompt-template.md) ·
  [competition study](docs/competition-study.md)

## License

MIT — see [LICENSE](LICENSE).
