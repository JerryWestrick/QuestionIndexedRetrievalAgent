# Example: EU AI Act Corpus

Build a QIRA corpus from **Regulation (EU) 2024/1689** — the EU Artificial Intelligence Act. A second reference QI builder, parallel to `examples/python-stdlib`, demonstrating the pipeline against a completely different source format (Formex 4 XML legal text instead of Sphinx RST).

## Why This Example Exists

The python-stdlib corpus is a faithful end-to-end demo, but it has a marketing problem: every modern LLM has the Python standard library memorised. Searching it via QIRA produces correct answers, but the LLM would have produced the same answers without it. The retrieval value is invisible.

The EU AI Act is the opposite. It was published in the *Official Journal* on 12 July 2024, after most public LLM training cutoffs. Models routinely confuse its articles with GDPR, hallucinate obligations, mix up the high-risk classification rules, and invent definitions that sound plausible but aren't in the text. Side-by-side with QIRA the difference is stark.

It is also a corpus that maps directly onto the buyer persona QIRA targets: governments, legal/compliance teams, regulators, and AI service providers who need an LLM to answer questions about a long, cross-referenced body of regulation **accurately, citing the source**.

## What This Produces

A corpus directory ready for the QIRA runtime (`qira_search` / `qira_read`):

```
output/eu-ai-act/
  eu-ai-act.db       # SQLite — sections with pre-formatted markdown
  chroma/            # ChromaDB — question vector index
  corpus.md          # Corpus identity for qira --initialize
```

## Source: Formex 4 XML from EUR-Lex

The Publications Office of the EU distributes every Official Journal act as a ZIP bundle of **Formex 4 XML** files. Formex (Formalised Exchange of Electronic Publications) is the schema the Publications Office has used for OJ documents since the early 2000s; the AI Act uses Formex 06.02.1.

For Regulation 2024/1689 the bundle contains:

```
L_202401689EN.toc.fmx.xml      # OJ table-of-contents wrapper (1 KB)
L_202401689EN.doc.fmx.xml      # Document manifest — points at main act + 13 annex files (5 KB)
L_202401689EN.000101.fmx.xml   # The main act: title, preamble (180 recitals), enacting terms (113 articles) (640 KB)
L_202401689EN.012401.fmx.xml   # Annex I
L_202401689EN.012601.fmx.xml   # Annex II
L_202401689EN.012701.fmx.xml   # Annex III  (high-risk AI systems)
L_202401689EN.013001.fmx.xml   # Annex IV   (technical documentation)
L_202401689EN.013201.fmx.xml   # Annex V
L_202401689EN.013301.fmx.xml   # Annex VI
L_202401689EN.013401.fmx.xml   # Annex VII
L_202401689EN.013601.fmx.xml   # Annex VIII
L_202401689EN.013801.fmx.xml   # Annex IX
L_202401689EN.013901.fmx.xml   # Annex X
L_202401689EN.014101.fmx.xml   # Annex XI
L_202401689EN.014301.fmx.xml   # Annex XII
L_202401689EN.014401.fmx.xml   # Annex XIII
```

### The Formex 4 element vocabulary used by this regulation

The schema is large in principle, but Regulation 2024/1689 uses a *small, regular* subset that maps cleanly to markdown. The complete element set the parser handles:

| Formex element | Meaning | Markdown rendering |
|---|---|---|
| `<DIVISION>` (recursive) | Chapter / Section / Subsection container | Section nesting |
| `<TITLE>/<TI>/<P>` + `<STI>/<P>` | Division heading + subtitle ("CHAPTER I" / "GENERAL PROVISIONS") | Section title |
| `<ARTICLE IDENTIFIER="001">` | Article (stable ID attribute) | Section |
| `<TI.ART>` + `<STI.ART>/<P>` | "Article 1" + "Subject matter" | Section title `Article 1 — Subject matter` |
| `<PARAG IDENTIFIER="001.001">` + `<NO.PARAG>1.</NO.PARAG>` + `<ALINEA>` | Numbered article paragraph | `**1.** {text}` |
| `<ALINEA>` | Plain paragraph (may contain `<P>` + `<LIST>`) | Markdown paragraph |
| `<LIST TYPE="alpha\|ARAB">/<ITEM>/<NP>` | Numbered/lettered list | `- (a) ...` / `- (1) ...` |
| `<NP>/<NO.P>` + `<TXT>` | Numbered point | List item |
| `<HT TYPE="ITALIC">` | Italic | `*x*` |
| `<HT TYPE="BOLD">` | Bold | `**x**` |
| `<HT TYPE="UC">` | Uppercase | uppercased text |
| `<DATE ISO="...">13 June 2024</DATE>` | Date with ISO attribute | text content (ISO dropped) |
| `<QUOT.START CODE="2018"/>x<QUOT.END CODE="2019"/>` | Defined-term single quotes | `'x'` (Unicode 2018/2019) |
| `<NOTE NOTE.ID="E0001">` | Footnote (always to external OJ acts) | Dropped |
| `<REF.DOC.OJ COLL="L" ...>OJ L 218, ...</REF.DOC.OJ>` | External OJ citation | text content |
| `<?PAGE NO="N"?>` | Page break processing instruction | Dropped |
| `<GR.CONSID>/<CONSID>/<NP>` | Recital group / recital | Section per recital |
| `<CONTENTS>` (annex root) | Annex body wrapper | Section content |
| `<GR.SEQ LEVEL="1">/<TITLE>` | Annex sub-grouping (e.g. "Section A") | Subsection heading |

The "tables" in Annex III (high-risk AI areas) and Annex IV (technical documentation) are not CALS tables — they are nested `<LIST>` elements. No table parser needed.

### What Formex does NOT mark up

**Intra-document cross-references are plain text.** The phrases `Article 6(1)`, `Section B of Annex I`, `Chapter III, Section 2`, `Articles 102 to 109` are written as ordinary text inside `<ALINEA>` and `<TXT>` elements — Formex offers `<REFERENCE>`/`<REF.ART>`/`<REF.PARAG>` elements in the schema but Regulation 2024/1689 does not use them. (The whole 640 KB main file contains zero such elements; verified.)

The builder handles this with a regex-based xref-rewriting pass — the same approach used in `examples/python-stdlib` for backtick-quoted Python names. See **Step 5** below.

## Section Model

The QIRA hierarchy:

```
eu-ai-act:1                Recitals (group container)
eu-ai-act:1.1              Recital 1
eu-ai-act:1.2              Recital 2
...
eu-ai-act:1.180            Recital 180

eu-ai-act:2                Chapter I — General Provisions
eu-ai-act:2.1              Article 1 — Subject matter
eu-ai-act:2.2              Article 2 — Scope
eu-ai-act:2.3              Article 3 — Definitions
eu-ai-act:2.3.1            (1) 'AI system'
eu-ai-act:2.3.2            (2) 'risk'
...
eu-ai-act:2.3.68           (68) ...
eu-ai-act:2.4              Article 4 — AI literacy

eu-ai-act:3                Chapter II — Prohibited AI Practices
eu-ai-act:3.1              Article 5 — Prohibited AI practices

eu-ai-act:4                Chapter III — High-Risk AI Systems
eu-ai-act:4.1              Section 1 — Classification of AI systems as high-risk
eu-ai-act:4.1.1            Article 6 — Classification rules for high-risk AI systems
eu-ai-act:4.1.2            Article 7 — Amendments to Annex III
eu-ai-act:4.2              Section 2 — Requirements for high-risk AI systems
eu-ai-act:4.2.1            Article 8 — Compliance with the requirements
...

eu-ai-act:14               Chapter XIII — Final Provisions
eu-ai-act:14.N             Article 113 — Entry into force and application

eu-ai-act:15               Annex I
eu-ai-act:16               Annex II
eu-ai-act:17               Annex III — High-risk AI systems referred to in Article 6(2)
...
eu-ai-act:27               Annex XIII
```

### Granularity decisions

| Unit | Treated as a QIRA section? | Why |
|---|---|---|
| Recitals (180) | Yes — each recital atomic | Recitals are quoted individually in legal argument; users ask "what does Recital 27 say about transparency?" |
| Chapters (~13) | Yes — has children, no own content | Lets the LLM browse "what's in Chapter III" and follow the children list |
| Sections / Subsections (~17) | Yes — has children, no own content | Same reason; preserves the structural map |
| Articles (113) | Yes — primary readable unit | The natural granularity for legal questions |
| Article 3 definitions (68) | Yes — each definition is a child of Article 3 | Without this, "what does 'provider' mean?" returns the entire 68-definition wall of text |
| Article paragraphs (`<PARAG>`) | **No** — kept inline within the article's `read_entry` | Paragraph-level granularity over-shards retrieval; better to return the whole article and let the LLM read it |
| Annexes (13) | Yes — each annex atomic | Annexes are short and naturally self-contained |

Article paragraph IDs (`<PARAG IDENTIFIER="001.002">`) from the source are preserved in the rendered markdown so the LLM can cite "Article 1(2)" precisely, even though the `read_entry` is the whole article.

### ID scheme

Pure dot-separated numeric, per the [QI/RA interface contract](../../docs/qi-ra-interface.md). The structural label ("Article 6", "Recital 27", "Annex III") lives in the section *title*, not the ID. Cross-references rewritten by the builder put both forms in the LLM's reach: `Article 6(1) (see eu-ai-act:4.1.1)`.

## Pipeline Steps

### 1. Get the Source

```bash
mkdir -p /tmp/eu-ai-act-source && cd /tmp/eu-ai-act-source
curl -sSL -H "Accept: application/zip" \
  -o fmx.zip \
  "http://publications.europa.eu/resource/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1.0006.02/DOC_1"
unzip fmx.zip
ls L_202401689EN.*.fmx.xml
```

The cellar URL is the resolved manifestation pointer — the more discoverable
`http://publications.europa.eu/resource/oj/L_202401689.ENG.fmx4` content-negotiates to an RDF descriptor that contains the same cellar URL. Either route works.

License: Commission Decision 2011/833/EU. Default reuse is **CC BY 4.0** — redistribute freely with attribution to EUR-Lex / Publications Office of the European Union.

### 2. Parse Formex XML → Section Tree (Format-Specific Adapter)

The adapter (`build_corpus.py`) does two things:

**2a. Manifest** — read `L_202401689EN.doc.fmx.xml` to get the main act file (`<DOC.MAIN.PUB>`) and the ordered list of 13 annex files (`<DOC.SUB.PUB TYPE="ANNEX">`).

**2b. Walk the XML** — use `xml.etree.ElementTree` to build a `Section` tree:

- Main act `<ACT>` → recitals group + chapter tree
- `<PREAMBLE>/<GR.CONSID>/<CONSID>` → one section per recital
- `<ENACTING.TERMS>/<DIVISION>` → recursive: each `<DIVISION>` becomes a chapter/section/subsection container
- `<DIVISION>/<ARTICLE>` → article section with all `<PARAG>`s rendered inline
- `<ARTICLE IDENTIFIER="003">` (Definitions) → special-case: each `<ITEM>` in the body becomes a child section (one definition per child)
- Each `<ANNEX>` file → one top-level annex section

XML inline elements (`<HT>`, `<DATE>`, `<QUOT.START>`, `<NOTE>`, `<REF.DOC.OJ>`, `<?PAGE?>`) are converted to markdown inline by a small dispatch function. Unknown elements pass through as text content (defensive default).

This is the **only format-specific step** — everything downstream is shared infrastructure copied from `examples/python-stdlib`.

### 3. Organize Sections — Assign IDs and Breadcrumbs

Same algorithm as python-stdlib: walk the section tree, assign hierarchical numeric IDs, build breadcrumbs from the title path. See `organize()` in `build_corpus.py`.

Breadcrumb form: `EU AI Act > Chapter III — High-Risk AI Systems > Section 2 — Requirements > Article 9 — Risk management system`.

### 4. Rewrite Cross-References

Regex pass over `content_md` for each section. Patterns recognised:

| Pattern (regex sketch) | Example match | Rewritten as |
|---|---|---|
| `Article (\d+)(?:\((\d+)\))?` | `Article 6(1)` | `Article 6(1) (see eu-ai-act:4.1.1)` |
| `Annex ([IVX]+)` | `Annex III` | `Annex III (see eu-ai-act:17)` |
| `Recital \((\d+)\)` / `recital \((\d+)\)` | `Recital (27)` | `Recital (27) (see eu-ai-act:1.27)` |
| `Chapter ([IVX]+)` | `Chapter III` | `Chapter III (see eu-ai-act:4)` |

Cross-references that don't resolve (e.g. articles outside the corpus, malformed citations) are left untouched.

### 5. Generate Questions (LLM Call)

Same as python-stdlib. For each section, `keprompt` is invoked with `generate_questions.prompt`, passing the section's breadcrumb, title, and content. The LLM returns a list of questions the section can answer; those become the search index.

The prompt is lightly adapted for legal/regulatory content — it asks for questions a compliance officer, lawyer, or AI builder would actually ask (e.g. "Are biometric categorisation systems prohibited?" rather than "What does the section say?").

Cost estimate: ~400 sections × ~$0.0007/section ≈ **$0.30** total (Cerebras `gpt-oss-120b`).

### 6. Pre-Format Markdown Entries

Identical to python-stdlib. `search_entry` = breadcrumb + question bullets + excerpt; `read_entry` = h1 heading + breadcrumb + full content + `## Subsections` list.

### 7. Vectorize and Store

Identical to python-stdlib. SQLite `sections` table + ChromaDB `questions` collection + `corpus.md`.

## Running the Build

```bash
# From the QIRA project root
cd examples/eu-ai-act

# Build the corpus
../../.venv/bin/python3 build_corpus.py \
  --source /tmp/eu-ai-act-source \
  --output ../../test-corpus/eu-ai-act
```

`--source` must contain the extracted Formex files (`L_202401689EN.doc.fmx.xml`, `L_202401689EN.000101.fmx.xml`, and the 13 annex files).

The script will pause and confirm before making LLM calls — same pattern as python-stdlib.

## Verifying the Corpus

```bash
# Search
echo '{"corpus":"eu-ai-act","question":"Which AI practices are prohibited?"}' \
  | ../../runtime/qira qira_search

# Read
echo '{"section_id":"eu-ai-act:3.1"}' \
  | ../../runtime/qira qira_read
```

## Installing the Corpus

Copy the output directory into your keprompt project's `prompts/functions/qira-corpus/`:

```bash
cp -r ../../test-corpus/eu-ai-act /path/to/your/project/prompts/functions/qira-corpus/
/path/to/your/project/prompts/functions/qira --initialize
```

The EU AI Act is now available to the LLM via `qira_search(corpus="eu-ai-act", ...)`.

## What Carries Over from python-stdlib, What Doesn't

| Stage | python-stdlib (RST) | eu-ai-act (Formex 4) |
|---|---|---|
| Parse source | `docutils`-style line scanner detecting heading underlines + `.. directive::` blocks | `xml.etree.ElementTree` walker over `<DIVISION>` / `<ARTICLE>` / `<PARAG>` |
| Inline cleanup | `:func:`/`:class:`/`:mod:` role substitution; `::` literal blocks → fenced code | `<HT>` → markdown emphasis; `<QUOT.START>` → curly quotes; `<DATE>` → text |
| Build section tree | Recursive descent with heading-rank tracking | Recursive descent over `<DIVISION>` containers |
| Organize / IDs / breadcrumbs | **Shared** (same `organize()`) | **Shared** |
| Cross-reference rewriting | Backtick-name → ID lookup | Plain-text regex → ID lookup |
| Question generation | **Shared** keprompt invocation | **Shared** |
| Pre-format `search_entry` / `read_entry` | **Shared** (same `preformat_entries()`) | **Shared** |
| Store SQLite + ChromaDB | **Shared** (same `store_corpus()`) | **Shared** |

The bespoke part is small. Most of `build_corpus.py` is copy-pasted from python-stdlib with `CORPUS = "eu-ai-act"` and a different parser at the top.
