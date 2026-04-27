# Example: EU AI Act Corpus

A pre-built QIRA corpus for **Regulation (EU) 2024/1689** — the EU Artificial Intelligence Act. Drop the zip into a keprompt project and your LLM can answer questions about the AI Act grounded in the official text instead of guessing from its training data.

## Who and License

- **Corpus:** EU AI Act — Regulation (EU) 2024/1689
- **Source:** [EUR-Lex CELEX 32024R1689](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689) — Formex 4 XML bundle
- **Source license:** CC BY 4.0 (Commission Decision 2011/833/EU — EUR-Lex default reuse)
- **Corpus license:** CC BY 4.0
- **Author:** Jerry Westrick &lt;jerry@westrick.com&gt;
- **Builder:** `build_corpus.py` in this directory

**No warranty.** This corpus is offered in good faith as an example. The author takes no responsibility for its correctness, completeness, or legality. **You are responsible for the veracity and legality of any use you make of it.**

The builder script is included as a working example — you are equally responsible for its correctness. If the corpus matters to your use case, rebuild your own from the authoritative source and verify the result.

**Need a production-grade corpus?** The author builds private and custom corpora on commercial terms. Contact: jerry@westrick.com.

## Try it in 2 minutes

**You'll need:** Python 3.12+, `curl`, `unzip`, and an LLM API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CEREBRAS_API_KEY`, ...).

```bash
curl -L https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/examples/eu-ai-act/try-eu-ai-act.sh | bash
```

The installer creates `./eu-ai-act-test/` in the current directory, builds a Python venv, installs `keprompt`, `faiss-cpu`, and `model2vec`, downloads the corpus zip, and writes a demo prompt. It does *not* export your API key and does *not* run the LLM — it prints the final commands for you to run.

When it finishes, the printed instructions are:

```bash
cd eu-ai-act-test
source .venv/bin/activate
export OPENAI_API_KEY=sk-...     # or ANTHROPIC_API_KEY, CEREBRAS_API_KEY, etc.
keprompt chat new eu-ai-act-demo
```

The LLM calls `qira_search`, reads the relevant sections, and answers with citations like `eu-ai-act:3.1`. On `openai/gpt-4o-mini` the run takes ~10 seconds of wall time and costs well under a cent. The first `qira_search` call also downloads the Model2Vec embedding model (~30 MB) from HuggingFace; subsequent calls are local and offline.

To ask a different question without editing the prompt:

```bash
keprompt chat new eu-ai-act-demo --set question="Who must register a high-risk AI system?"
```

### Prefer to do it by hand?

Read [`try-eu-ai-act.sh`](try-eu-ai-act.sh) — it's a short, commented bash script. Or follow the step-by-step [QUICKSTART.md](../../QUICKSTART.md) at the repo root, which walks the same install with a separate plumbing-test stage that doesn't need an LLM.

## What's in the corpus

The corpus mirrors the structure of Regulation (EU) 2024/1689, with one QIRA section per natural unit of the act:

| Unit | Sections | Notes |
|---|---|---|
| Recitals | 180 | One section per recital — quoted individually in legal argument |
| Chapters | 13 | Container sections with no own content; child list lets the LLM browse |
| Sections / Subsections | ~17 | Same — structural map of the act |
| Articles | 113 | Primary readable unit; whole article returned by `qira_read` |
| Article 3 definitions | 68 | Each definition is a child of Article 3 (otherwise the whole 68-definition wall comes back as one hit) |
| Annexes | 13 | Each annex atomic |

IDs are pure dot-separated numerics (`eu-ai-act:4.1.1` = Chapter III → Section 1 → Article 6). The structural label ("Article 6", "Recital 27", "Annex III") lives in the section title, not the ID. The builder rewrites intra-document cross-references inline so the LLM sees both forms together: `Article 6(1) (see eu-ai-act:4.1.1)`.

A worked example is in [QIRA_Article.md §6](../../QIRA_Article.md), with full retrieval traces in Appendices A and B.

## Build your own from the EUR-Lex source

The included `build_corpus.py` is a complete, working builder — included so you can rebuild the corpus from the authoritative source if the corpus matters to your use case, or fork it as a template for any other Formex 4 EUR-Lex regulation.

Outline:

1. Download the Formex 4 ZIP bundle for [CELEX 32024R1689](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689) (license: CC BY 4.0 — Commission Decision 2011/833/EU).
2. Extract `L_202401689EN.*.fmx.xml` (1 manifest + 1 main act + 13 annex files).
3. Run `build_corpus.py --source <dir> --output <dir>`. The builder pauses before making LLM calls. Cost on Cerebras `gpt-oss-120b`: ~$0.30 (about 400 sections × ~$0.0007 each).
4. Zip the output and drop it into your project's `prompts/functions/`.

The Formex element vocabulary actually used by the AI Act is small and regular (`<DIVISION>`, `<ARTICLE>`, `<PARAG>`, `<ALINEA>`, `<LIST>`, `<HT>`, `<QUOT.START>`, `<DATE>`, `<NOTE>`, `<REF.DOC.OJ>`). Read `build_corpus.py` for the full mapping — it's commented and runs to ~1100 lines. About 80% of it is shared with `examples/python-stdlib/build_corpus.py` (organize → assign IDs, generate questions via keprompt, pre-format markdown, store SQLite + FAISS); only the source parser at the top is bespoke.

For the deeper rationale (why the granularity decisions, why regex xref rewriting, why per-recital sections), see the older builder-voice version of this file in git: `git log --diff-filter=D --follow examples/eu-ai-act/README.md` to find the commit, then `git show <commit>:examples/eu-ai-act/README.md`.
